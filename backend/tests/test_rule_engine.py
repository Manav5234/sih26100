"""Phase 5: deterministic rule engine — every verdict must trace to config."""
import pytest

from app.rule_engine import (
    _critical_override_fired,
    _entity_result,
    _tender_dict,
    evaluate_rule,
    load_config,
    parse_condition,
)

RULES = {r["rule_id"]: r for r in load_config()["rules"]}


def tender(**overrides) -> dict:
    base = _tender_dict.__wrapped__ if hasattr(_tender_dict, "__wrapped__") else None
    base = {
        "minimum_turnover": None, "required_msme_tier": None,
        "local_content_requirement_applicable": False, "bid_value_cr": None,
        "required_local_content_class": None, "required_oem": None,
        "tender_ref": "GEM/2026/T/TEST", "title": "Test",
    }
    base.update(overrides)
    return base


def ev(**blocks) -> dict:
    return {**blocks}


# --- config stays parseable (guard for officer edits) -----------------------

def test_all_config_rules_parse():
    for rule in RULES.values():
        if rule.get("not_applicable_when"):
            parse_condition(rule["not_applicable_when"])
        parse_condition(rule["condition"])
        for expr in rule.get("classification", {}).values():
            parse_condition(expr)
        assert rule["pass"] in {"SATISFIED", "VIOLATION", "NOT_VERIFIED",
                                "CONFLICT", "NOT_APPLICABLE"}
        assert rule["fail"] in {"SATISFIED", "VIOLATION", "NOT_VERIFIED",
                                "CONFLICT", "NOT_APPLICABLE"}


# --- (a) not_applicable_when fires BEFORE the condition is touched ----------

def test_not_applicable_when_evaluated_before_condition():
    rule = dict(RULES["MSME-CLASS-001"])
    rule["condition"] = "THIS IS NOT PARSEABLE ?!?"      # would raise if touched
    result = evaluate_rule(rule, ev(), tender(required_msme_tier=None))
    assert result["verdict"] == "NOT_APPLICABLE"


# --- (c) simple boolean rules ----------------------------------------------

def test_boolean_rule_pass_fail_and_missing():
    rule = RULES["GST-001"]
    assert evaluate_rule(rule, ev(gst={"status": "Active"}), tender())["verdict"] == "SATISFIED"
    assert evaluate_rule(rule, ev(gst={"status": "Suspended"}), tender())["verdict"] == "VIOLATION"
    # document absent -> on_source_unreachable, never VIOLATION
    assert evaluate_rule(rule, ev(), tender())["verdict"] == "NOT_VERIFIED"


def test_missing_evidence_never_violation():
    rule = RULES["DEBARMENT-001"]
    result = evaluate_rule(rule, ev(), tender())
    assert result["verdict"] == "NOT_VERIFIED"


# --- (b) classify-then-compare ---------------------------------------------

@pytest.mark.parametrize("turnover,investment,expected", [
    (4.5, 2.0, "SATISFIED"),      # micro, in ['micro','small']
    (40.0, 10.0, "SATISFIED"),    # small (<100cr/<25cr), in ['micro','small']
    (200.0, 60.0, "VIOLATION"),   # medium (>=100cr), not in list
    (600.0, 200.0, "VIOLATION"),  # beyond every configured tier (large)
])
def test_classify_then_compare_msme(turnover, investment, expected):
    rule = RULES["MSME-CLASS-001"]
    evidence = ev(bidder={"turnover_cr": turnover, "investment_cr": investment})
    result = evaluate_rule(rule, evidence, tender(required_msme_tier=["micro", "small"]))
    assert result["verdict"] == expected


def test_classify_missing_input_is_not_verified():
    rule = RULES["MSME-CLASS-001"]
    result = evaluate_rule(rule, ev(bidder={}), tender(required_msme_tier=["micro"]))
    assert result["verdict"] == "NOT_VERIFIED"


@pytest.mark.parametrize("pct,expected", [
    (60, "SATISFIED"),     # class_1 >= required class_2
    (30, "SATISFIED"),     # class_2 == required class_2
    (10, "VIOLATION"),     # non_local below required class
])
def test_meets_or_exceeds_uses_config_class_order(pct, expected):
    rule = RULES["LOCAL-CONTENT-001"]
    evidence = ev(bidder={"local_content_pct": pct})
    t = tender(local_content_requirement_applicable=True, bid_value_cr=80,
               required_local_content_class="class_2_local_supplier")
    assert evaluate_rule(rule, evidence, t)["verdict"] == expected


def test_local_content_not_applicable_when_bid_above_200cr():
    rule = RULES["LOCAL-CONTENT-001"]
    t = tender(local_content_requirement_applicable=True, bid_value_cr=250,
               required_local_content_class="class_1_local_supplier")
    assert evaluate_rule(rule, ev(bidder={"local_content_pct": 10}), t)["verdict"] == "NOT_APPLICABLE"


# --- (e) pass/fail values + thresholds come from config, not code ----------

def test_turnover_threshold_driven_by_tender_config():
    rule = RULES["TURNOVER-001"]
    evidence = ev(bidder={"turnover": 4.0})
    assert evaluate_rule(rule, evidence, tender(minimum_turnover=5.0))["verdict"] == "VIOLATION"
    # same code, different tender threshold -> opposite verdict
    assert evaluate_rule(rule, evidence, tender(minimum_turnover=3.0))["verdict"] == "SATISFIED"
    assert evaluate_rule(rule, evidence, tender(minimum_turnover=None))["verdict"] == "NOT_APPLICABLE"


# --- IF ... THEN conditions --------------------------------------------------

def test_if_then_guard_false_is_not_applicable():
    rule = RULES["LABOUR-EPFO-001"]
    assert evaluate_rule(rule, ev(bidder={"employee_count": 15}), tender())["verdict"] == "NOT_APPLICABLE"
    assert evaluate_rule(rule, ev(bidder={"employee_count": 25},
                                  epfo={"status": "REGISTERED"}), tender())["verdict"] == "SATISFIED"
    assert evaluate_rule(rule, ev(bidder={"employee_count": 25}), tender())["verdict"] == "NOT_VERIFIED"


def test_informational_rule_condition_is_na():
    assert evaluate_rule(RULES["GST-002"], ev(), tender())["verdict"] == "NOT_APPLICABLE"
    assert evaluate_rule(RULES["MSE-PURCHASE-PREF-001"], ev(), tender())["verdict"] == "NOT_APPLICABLE"


def test_matches_treats_unspecified_oem_as_satisfied():
    rule = RULES["OEM-AUTH-001"]
    evidence = ev(bidder={"is_oem": False},
                  authorization={"present": True, "oem_name": "ACME Motors"})
    # no OEM specified on tender -> constraint absent
    assert evaluate_rule(rule, evidence, tender(required_oem=None))["verdict"] == "SATISFIED"
    assert evaluate_rule(rule, evidence, tender(required_oem="ACME Motors"))["verdict"] == "SATISFIED"
    assert evaluate_rule(rule, evidence, tender(required_oem="Other Corp"))["verdict"] == "VIOLATION"


# --- ENTITY condition chain also parses (evaluate_bidder uses stored path) ---

def test_entity_condition_chain_is_evaluable():
    rule = RULES["ENTITY-CONSISTENCY-001"]
    evidence = ev(pan={"legal_name": "ABC Technologies Pvt Ltd"},
                  gst={"legal_name": "ABC Technologies Pvt Ltd"},
                  udyam={"legal_name": "ABC Tech Solutions"})
    assert evaluate_rule(rule, evidence, tender())["verdict"] == "CONFLICT"


# --- Phase 4 stored result wiring -------------------------------------------

def test_entity_result_uses_stored_comparison():
    cfg = RULES["ENTITY-CONSISTENCY-001"]
    page_refs = [{"source": "PAN", "field": "name", "document_id": "d1", "page": 1}]
    assert _entity_result(cfg, {"verdict": "MATCH", "page_refs": page_refs})["verdict"] == "SATISFIED"
    assert _entity_result(cfg, {"verdict": "CONFLICT", "page_refs": page_refs})["verdict"] == "CONFLICT"
    assert _entity_result(cfg, {"verdict": "NOT_VERIFIED", "page_refs": []})["verdict"] == "NOT_VERIFIED"
    assert _entity_result(cfg, None)["verdict"] == "NOT_VERIFIED"
    refs = _entity_result(cfg, {"verdict": "MATCH", "page_refs": page_refs})["evidence_refs"]
    assert refs[0]["document_id"] == "d1" and refs[0]["path"] == "pan.legal_name"


# --- critical override flag (Phase 6 reads this) ----------------------------

def test_critical_override_flag():
    critical = ["DEBARMENT-001", "ENTITY-CONSISTENCY-001"]
    conflict = {"rule_id": "ENTITY-CONSISTENCY-001", "verdict": "CONFLICT"}
    violation = {"rule_id": "DEBARMENT-001", "verdict": "VIOLATION"}
    other = {"rule_id": "GST-001", "verdict": "VIOLATION"}
    not_crit = {"rule_id": "ENTITY-CONSISTENCY-001", "verdict": "NOT_VERIFIED"}
    assert _critical_override_fired([conflict], critical) is True
    assert _critical_override_fired([violation], critical) is True
    assert _critical_override_fired([other], critical) is False     # critical = these two only
    assert _critical_override_fired([not_crit], critical) is False  # NOT_VERIFIED doesn't fire


# --- evidence trail on every result -----------------------------------------

def test_result_carries_evidence_trail():
    rule = RULES["GST-001"]
    result = evaluate_rule(rule, ev(gst={"status": "Active"},
                                    _refs={"gst.status": {"origin": "document",
                                                          "doc_type": "GST",
                                                          "document_id": "doc-1",
                                                          "field": "status", "page": 1}}),
                           tender())
    assert result["legal_citation"].startswith("Central Goods and Services Tax Act")
    assert result["evidence_refs"][0]["document_id"] == "doc-1"
    assert result["source"] == ["GST:doc-1"]
