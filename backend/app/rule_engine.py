"""Deterministic rule engine (Phase 5).

Its ONLY job: read app/config/rules_config.json at evaluation time and
evaluate each rule against a bidder+tender's available evidence. Thresholds,
conditions, pass/fail verdicts, applicability — all come from the JSON.
Changing rules_config.json is sufficient; no code change required.

This module implements only a generic expression language:
  - operators: ==  !=  >  >=  <  <=  AND  OR  is null  is not null  is in
    matches  "meets or exceeds" (ordinal over the config's class_order)
  - functions: classify(...)  normalize(...)   — classification data comes
    from the rule's own "classification" object
  - Kleene three-valued logic: missing evidence -> UNKNOWN -> NOT_VERIFIED
    (never silently VIOLATION; see on_source_unreachable)
  - IF <guard> THEN <body> conditions -> NOT_APPLICABLE when guard is false
  - conditions starting with "N/A" (informational rules) -> NOT_APPLICABLE

Deliberate wiring (not business logic):
  - ENTITY-CONSISTENCY-001 reads Phase 4's stored comparison result instead
    of re-computing name normalization.
  - pan.format_valid is derived with the same KEY_FORMATS check Phase 3
    already used to validate stored identifiers.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import (MockDebarmentAdapter, MockGSTAdapter, MockPANAdapter,
                          MockUdyamAdapter)
from app.audit import audit
from app.database import engine
from app.db.models import (Bidder, Document, Requirement, RuleResult, Tender,
                           Verification)
from app.extraction import KEY_FORMATS, _id_candidate

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config" / "rules_config.json"

VERDICT_NA = "NOT_APPLICABLE"
VERDICT_NV = "NOT_VERIFIED"
FAILURE_VERDICTS = ("VIOLATION", "CONFLICT")


class RuleParseError(Exception):
    """Condition text is not parseable — fail loud rather than invent a verdict."""


# --- config -----------------------------------------------------------------

def load_config() -> dict:
    """Fresh read every evaluation: edit the JSON, take effect immediately."""
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


# --- tokenizer / parser -----------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s*(\d+(?:\.\d+)?|'[^']*'|<=|>=|==|!=|<|>|[(),]|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)"
)


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise RuleParseError(f"cannot tokenize at {text[pos:pos + 40]!r}")
        token = match.group(1)
        if token[0].isdigit():
            kind = "num"
        elif token[0] == "'":
            kind = "str"
        elif token[0] in "<>=!":
            kind = "op"
        elif token in "(),":
            kind = "punct"
        else:
            kind = "word"
        tokens.append((kind, token))
        pos = match.end()
    return tokens


def parse_condition(raw: str):
    """Condition text -> AST. Handles prose forms found in the config:
    leading 'N/A', 'IF ... THEN ...', trailing '(if specified)'."""
    text = re.sub(r"\s*\(if specified\)", "", raw, flags=re.IGNORECASE).strip()
    if text.upper().startswith("N/A"):
        return ("na",)
    tokens = _tokenize(text)
    if tokens and tokens[0][0] == "word" and tokens[0][1].upper() == "IF":
        then_at = next((i for i, t in enumerate(tokens)
                        if t[0] == "word" and t[1].upper() == "THEN"), None)
        if then_at is None:
            raise RuleParseError(f"IF without THEN: {raw!r}")
        guard = _Parser(tokens[1:then_at]).parse_all()
        body = _Parser(tokens[then_at + 1:]).parse_all()
        return ("if", guard, body)
    return _Parser(tokens).parse_all()


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def next(self):
        tok = self.peek()
        self.i += 1
        return tok

    def at_word(self, *words) -> bool:
        tok = self.peek()
        return bool(tok) and tok[0] == "word" and tok[1].upper() in words

    def parse_all(self):
        node = self.parse_or()
        if self.i != len(self.tokens):
            raise RuleParseError(f"unexpected token {self.tokens[self.i]!r}")
        return node

    def parse_or(self):
        nodes = [self.parse_and()]
        while self.at_word("OR"):
            self.next()
            nodes.append(self.parse_and())
        return nodes[0] if len(nodes) == 1 else ("or", nodes)

    def parse_and(self):
        nodes = [self.parse_cmp()]
        while self.at_word("AND"):
            self.next()
            nodes.append(self.parse_cmp())
        return nodes[0] if len(nodes) == 1 else ("and", nodes)

    def parse_cmp(self):
        left = self.parse_primary()
        steps = []
        while True:
            op = self._take_op()
            if op is None:
                break
            if op in ("isnull", "isnotnull"):
                steps.append((op, None))       # unary: no right operand
            else:
                steps.append((op, self.parse_primary()))
        if not steps:
            return left
        return ("cmp", left, steps)

    def _take_op(self):
        tok = self.peek()
        if tok is None:
            return None
        if tok[0] == "op":
            self.next()
            return tok[1]
        if tok[0] == "word":
            word = tok[1].upper()
            if word == "IS":
                self.next()
                nxt = self.next()
                if nxt and nxt[0] == "word" and nxt[1].upper() == "NULL":
                    return "isnull"
                if nxt and nxt[0] == "word" and nxt[1].upper() == "NOT":
                    after = self.next()
                    if not (after and after[0] == "word" and after[1].upper() == "NULL"):
                        raise RuleParseError("expected 'is not null'")
                    return "isnotnull"
                if nxt and nxt[0] == "word" and nxt[1].upper() == "IN":
                    return "in"
                raise RuleParseError(f"unsupported 'is' phrase after {tok!r}")
            if word == "MATCHES":
                self.next()
                return "matches"
            if word == "MEETS" and self.tokens[self.i + 1:self.i + 3] == \
                    [("word", "or"), ("word", "exceeds")]:
                self.next(); self.next(); self.next()
                return "ge_class"
        return None

    def parse_primary(self):
        tok = self.peek()
        if tok is None:
            raise RuleParseError("unexpected end of condition")
        kind, text = tok
        if kind == "num":
            self.next()
            return ("lit", float(text) if "." in text else int(text))
        if kind == "str":
            self.next()
            return ("lit", text[1:-1])
        if kind == "punct":
            if text == "(":
                self.next()
                node = self.parse_or()
                close = self.next()
                if close != ("punct", ")"):
                    raise RuleParseError("missing ')'")
                return node
            if text == ")":
                raise RuleParseError("stray ')'")
            raise RuleParseError(f"unexpected token {tok!r}")
        lower = text.lower()
        if lower in ("true", "false", "null"):
            self.next()
            return ("lit", {"true": True, "false": False, "null": None}[lower])
        nxt = self.tokens[self.i + 1] if self.i + 1 < len(self.tokens) else None
        if nxt == ("punct", "("):
            return self._parse_call()
        self.next()
        return ("path", text)

    def _parse_call(self):
        name_tok = self.next()          # function name
        self.next()                     # '('
        args = []
        if self.peek() == ("punct", ")"):
            self.next()
            return ("call", name_tok[1], args)
        while True:
            args.append(self.parse_or())
            tok = self.next()
            if tok == ("punct", ")"):
                break
            if tok == ("punct", ","):
                continue
            raise RuleParseError(f"unexpected token {tok!r} in call {name_tok[1]!r}")
        return ("call", name_tok[1], args)


def collect_paths(node) -> list[str]:
    """Every evidence path referenced by an AST, in encounter order."""
    paths: list[str] = []
    seen: set[str] = set()

    def walk(n):
        if not isinstance(n, tuple):
            return
        if n[0] == "path":
            if n[1] not in seen:
                seen.add(n[1])
                paths.append(n[1])
        elif n[0] == "cmp":
            walk(n[1])
            for _op, right in n[2]:
                walk(right)
        else:
            for child in n[1:]:
                if isinstance(child, list):
                    for c in child:
                        walk(c)
                else:
                    walk(child)

    walk(node)
    return paths


# --- evaluation (three-valued logic) ---------------------------------------

class _Missing:
    """Path absent from evidence — distinct from a present null."""

    def __repr__(self):
        return "<MISSING>"


class _NoTier:
    """classify() matched no tier with inputs present — a definitive miss."""

    def __repr__(self):
        return "<NO_TIER>"


MISSING = _Missing()
NO_TIER = _NoTier()


def _resolve(path: str, ev: dict, tender: dict):
    if "." not in path:
        bidder_block = ev.get("bidder")
        if isinstance(bidder_block, dict) and path in bidder_block:
            return bidder_block[path]
        return MISSING
    root, *rest = path.split(".")
    if root == "tender":
        current = tender
    elif root in ev:
        current = ev[root]
    else:
        return MISSING
    for part in rest:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return MISSING
    return current


def _kleene_and(values):
    if any(v is False for v in values):
        return False
    if any(v is None for v in values):
        return None
    return True


def _kleene_or(values):
    if any(v is True for v in values):
        return True
    if any(v is None for v in values):
        return None
    return False


def _equal(a, b) -> bool | None:
    if a is MISSING or b is MISSING or a is None or b is None:
        return None
    if isinstance(a, str) and isinstance(b, str):
        return a.casefold() == b.casefold()      # documents print 'Active', rules say 'ACTIVE'
    return a == b


def _eval_value(node, ev, tender, rule):
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "path":
        return _resolve(node[1], ev, tender)
    if kind == "call":
        name, args = node[1].lower(), node[2]
        if name == "classify":
            return _classify(rule, args, ev, tender)
        if name == "normalize":
            from app.entity_resolution import normalize_entity_name
            values = [_eval_value(a, ev, tender, rule) for a in args]
            if any(v is MISSING or v is None for v in values):
                return MISSING
            return normalize_entity_name(values[0])
        raise RuleParseError(f"unknown function {name!r}")
    truth = _eval_truth(node, ev, tender, rule)
    if truth is None:
        return MISSING
    return truth


def _classify(rule, arg_nodes, ev, tender):
    """Tier from the rule's own 'classification' object; first matching tier
    in config order wins (narrowest-first as written)."""
    for arg in arg_nodes:
        if _eval_value(arg, ev, tender, rule) is MISSING:
            return MISSING
    unknown_seen = False
    for tier, expr in rule.get("classification", {}).items():
        ast = parse_condition(expr)
        result = _eval_truth(ast, ev, tender, rule)
        if result is True:
            return tier
        if result is None:
            unknown_seen = True
    if unknown_seen:
        return MISSING
    return NO_TIER


def _eval_truth(node, ev, tender, rule) -> bool | None:
    kind = node[0]
    if kind == "lit":
        return bool(node[1])
    if kind == "path":
        value = _resolve(node[1], ev, tender)
        if value is MISSING or value is None:
            return None
        return bool(value)
    if kind == "call":
        value = _eval_value(node, ev, tender, rule)
        if value is MISSING:
            return None
        if value is NO_TIER:
            return False
        return bool(value)
    if kind == "and":
        return _kleene_and([_eval_truth(n, ev, tender, rule) for n in node[1]])
    if kind == "or":
        return _kleene_or([_eval_truth(n, ev, tender, rule) for n in node[1]])
    if kind == "cmp":
        return _eval_cmp(node, ev, tender, rule)
    raise RuleParseError(f"cannot evaluate node {kind!r}")


def _eval_cmp(node, ev, tender, rule) -> bool | None:
    left_node, steps = node[1], node[2]
    current = _eval_value(left_node, ev, tender, rule)
    results = []
    for op, right_node in steps:
        if right_node is None:                        # is null / is not null
            results.append(_compare(op, current, MISSING, left_node, None, rule))
            continue
        right = _eval_value(right_node, ev, tender, rule)
        results.append(_compare(op, current, right, left_node, right_node, rule))
        current = right                               # chained: a == b == c
    if len(results) == 1:
        return results[0]
    folded = results[0]
    for nxt in results[1:]:
        folded = _kleene_and([folded, nxt])
    return folded


def _compare(op, left, right, left_node, right_node, rule) -> bool | None:
    if op == "isnull":
        return left is MISSING or left is None
    if op == "isnotnull":
        return not (left is MISSING or left is None)
    if op == "in":
        # missing tender/bidder config first (never VIOLATION), then NO_TIER
        if left is MISSING or right is MISSING or right is None or left is None:
            return None
        if not isinstance(right, (list, tuple)):
            return None
        if left is NO_TIER:
            return False                      # classified beyond every tier: definitively not in list
        if isinstance(left, str):
            return any(isinstance(r, str) and r.casefold() == left.casefold() for r in right)
        return left in right
    if op == "matches":
        if right is MISSING or right is None:
            return True                       # constraint not specified -> nothing to violate
        return _equal(left, right)
    if op == "ge_class":
        return _ge_class(left, right, rule)
    if left is MISSING or right is MISSING or left is None or right is None:
        return None
    if op == "==":
        return _equal(left, right)
    if op == "!=":
        equal = _equal(left, right)
        return None if equal is None else not equal
    try:
        if op == ">=":
            return left >= right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == "<":
            return left < right
    except TypeError:
        return None
    raise RuleParseError(f"unknown operator {op!r}")


def _ge_class(left, right, rule) -> bool | None:
    """'meets or exceeds' — ordinal rank from the config's class_order."""
    order = rule.get("class_order")
    if not order:
        logger.error("rule %s uses 'meets or exceeds' but has no class_order in config",
                     rule.get("rule_id"))
        return None
    if left is MISSING or right is MISSING or left is None or right is None:
        return None
    if left is NO_TIER:
        return False
    if left not in order or right not in order:
        return None
    return order.index(left) >= order.index(right)


# --- rule / bidder evaluation ----------------------------------------------

def _unreachable_verdict(rule: dict) -> str:
    return rule.get("on_source_unreachable", VERDICT_NV)


def _evidence_refs(paths: list[str], ev: dict, tender: dict, refs_map: dict) -> list[dict]:
    out = []
    for path in paths:
        root = path.split(".")[0]
        if path in refs_map:
            value = _resolve(path, ev, tender)
            out.append({"path": path,
                        "value": None if value in (MISSING, NO_TIER) else value,
                        **refs_map[path]})
        elif root == "tender":
            value = _resolve(path, ev, tender)
            out.append({"path": path,
                        "value": None if value is MISSING else value,
                        "origin": "tender"})
        elif root in ev or "." not in path:
            value = _resolve(path, ev, tender)
            if value is MISSING:
                out.append({"path": path, "value": None, "origin": "unresolved",
                            "missing": True})
            else:
                out.append({"path": path,
                            "value": None if value is NO_TIER else value,
                            "origin": "bidder"})
        else:
            out.append({"path": path, "value": None, "origin": "unresolved",
                        "missing": True})
    return out


def _source_summary(refs: list[dict]) -> list[str]:
    sources: list[str] = []
    for ref in refs:
        origin = ref.get("origin")
        if origin == "document":
            label = f"{ref.get('doc_type')}:{ref['document_id']}"
        elif origin == "derived":
            label = f"derived:{ref.get('doc_type')}"
        elif origin == "adapter":
            label = ref.get("source", "adapter")
        elif origin in ("tender", "bidder", "stored"):
            label = origin
        else:
            continue
        if label not in sources:
            sources.append(label)
    return sources


def evaluate_rule(rule_config: dict, bidder_evidence: dict, tender: dict) -> dict:
    """Evaluate one rule from rules_config.json. Verdict order of checks:
    (a) not_applicable_when, (b/c) condition (classify() is data-driven),
    (d) missing evidence -> on_source_unreachable, (e) pass/fail values."""
    cfg = rule_config
    ev = bidder_evidence
    refs_map = ev.get("_refs", {})
    paths: list[str] = []

    # (a) applicability first — condition is not evaluated at all when true
    na = cfg.get("not_applicable_when")
    if na:
        na_ast = parse_condition(na)
        paths += collect_paths(na_ast)
        if _eval_truth(na_ast, ev, tender, cfg) is True:
            refs = _evidence_refs(paths, ev, tender, refs_map)
            return {"rule_id": cfg["rule_id"], "verdict": VERDICT_NA,
                    "evidence_refs": refs, "source": _source_summary(refs),
                    "legal_citation": cfg.get("source")}

    condition = cfg.get("condition", "")
    ast = parse_condition(condition)
    if ast[0] == "na":                      # informational rules ("N/A — ...")
        refs = _evidence_refs(paths, ev, tender, refs_map)
        return {"rule_id": cfg["rule_id"], "verdict": cfg.get("pass", VERDICT_NA),
                "evidence_refs": refs, "source": _source_summary(refs),
                "legal_citation": cfg.get("source")}

    if ast[0] == "if":                      # IF guard THEN body
        guard = _eval_truth(ast[1], ev, tender, cfg)
        if guard is False:
            refs = _evidence_refs(paths, ev, tender, refs_map)
            return {"rule_id": cfg["rule_id"], "verdict": VERDICT_NA,
                    "evidence_refs": refs, "source": _source_summary(refs),
                    "legal_citation": cfg.get("source")}
        if guard is None:
            refs = _evidence_refs(paths, ev, tender, refs_map)
            return {"rule_id": cfg["rule_id"], "verdict": _unreachable_verdict(cfg),
                    "evidence_refs": refs, "source": _source_summary(refs),
                    "legal_citation": cfg.get("source")}
        ast = ast[2]

    paths += collect_paths(ast)
    result = _eval_truth(ast, ev, tender, cfg)
    if result is True:
        verdict = cfg["pass"]
    elif result is False:
        verdict = cfg["fail"]
    else:                                   # (d) unknown: missing evidence
        verdict = _unreachable_verdict(cfg)
    refs = _evidence_refs(paths, ev, tender, refs_map)
    return {"rule_id": cfg["rule_id"], "verdict": verdict,
            "evidence_refs": refs, "source": _source_summary(refs),
            "legal_citation": cfg.get("source")}


# --- evidence assembly ------------------------------------------------------

# extraction field -> evidence path root/key (adapter: data wiring only)
_FIELD_MAP = {
    "PAN": ("pan", {"legal_name": "name", "number": "pan"}),
    # gst.status is NOT mapped from the certificate's printed line: registry
    # statuses come from adapters only (Phase 6.5).
    "GST": ("gst", {"legal_name": "legal_name", "number": "gstin"}),
    "UDYAM": ("udyam", {"legal_name": "enterprise_name",
                        "number": "udyam_number", "category": "category"}),
    "OEM_AUTHORIZATION": ("authorization", {"entity_name": "entity_name",
                                            "oem_name": "oem_name",
                                            "statement": "authorization_statement"}),
}

# Phase 6.7: document-sourced numeric attributes that live in the bidder
# evidence block (bare paths and bidder.* conditions resolve there).
_BIDDER_NUMERIC_FIELDS = (
    ("FINANCIAL", "turnover_cr", "turnover"),
    ("LOCAL_CONTENT", "local_content_pct", "local_content_pct"),
)

# evidence root -> (root/key of the extracted identifier, adapter)
# identifiers live under the out-key "number" (see _FIELD_MAP values);
# debarment is keyed by the PAN number: no debarment document exists.
_ADAPTER_CHECKS = (
    ("pan", "pan", "number", MockPANAdapter),
    ("gst", "gst", "number", MockGSTAdapter),
    ("udyam", "udyam", "number", MockUdyamAdapter),
    ("debarment", "pan", "number", MockDebarmentAdapter),
)


def _number(value) -> float | None:
    """Plain numeric evidence: parse exactly what's there, else null.
    '12.40' / '45%' -> number; 'Rs. 12 crore' -> null (no guessing)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().rstrip("%").strip().replace(",", ""))
    except ValueError:
        return None


def _verify_via_adapters(db: Session, bidder: Bidder, ev: dict, refs: dict) -> None:
    """Phase 6.5: registry statuses come from GovernmentSourceAdapter calls.

    No extracted identifier -> adapter is never called (missing document or
    redacted number): the status stays null and the rule stays NOT_VERIFIED
    because evidence is missing — not because of a fake adapter failure.
    Every call is audited into the verifications table."""
    for root, id_root, id_key, adapter_cls in _ADAPTER_CHECKS:
        identifier = ev.get(id_root, {}).get(id_key)
        if not identifier:
            continue
        response = adapter_cls().verify(identifier)
        refs[f"{root}.status"] = {
            "origin": "adapter", "source": response["source"],
            "identifier": identifier, "confidence": response["confidence"],
            "adapter_status": response["status"],
        }
        if response["status"] != "NOT_VERIFIED":     # unknown id stays null -> NOT_VERIFIED
            ev.setdefault(root, {})["status"] = response["status"]
        db.add(Verification(
            bidder_id=bidder.id, source=response["source"], identifier=identifier,
            status="NOT_FOUND" if response["status"] == "NOT_VERIFIED" else "MATCHED",
            matched_fields=response["matched_fields"],
            confidence=response["confidence"], response=response,
        ))
        audit(db, "SOURCE_CHECKED", tender_id=bidder.tender_id, bidder_id=bidder.id,
              detail={"source": response["source"], "identifier": identifier,
                      "status": response["status"],
                      "confidence": response["confidence"]})
    db.commit()   # audit rows persist even though evaluation is read-only


def build_bidder_evidence(db: Session, bidder: Bidder) -> dict:
    """Stored Phase 3 extractions -> evidence dict + per-path provenance
    under '_refs' (the evidence trail attached to every RuleResult)."""
    ev: dict = {"bidder": {"name": bidder.name, "legal_name": bidder.legal_name}}
    refs: dict[str, dict] = {}
    latest: dict[str, Document] = {}
    for doc in (db.query(Document).filter(Document.bidder_id == bidder.id)
                .order_by(Document.uploaded_at).all()):
        latest[doc.doc_type] = doc            # ascending order: later upload wins

    for doc_type, (root, field_map) in _FIELD_MAP.items():
        doc = latest.get(doc_type)
        if doc is None:
            continue
        block: dict = {}
        number_field = None
        for out_key, source_field in field_map.items():
            extracted = next((f for f in doc.extracted_fields
                              if f.field_name == source_field), None)
            if extracted is None or extracted.value is None:
                continue
            block[out_key] = extracted.value
            number_field = extracted if source_field == "pan" else number_field
            refs[f"{root}.{out_key}"] = {
                "origin": "document", "doc_type": doc_type,
                "document_id": str(doc.id), "field": source_field,
                "page": extracted.page, "confidence": extracted.confidence,
            }
        if doc_type == "PAN" and "number" in block:
            # same deterministic check Phase 3 used to reject truncated IDs
            block["format_valid"] = bool(re.match(
                KEY_FORMATS["PAN"], _id_candidate("PAN", block["number"])))
            refs["pan.format_valid"] = {
                "origin": "derived", "doc_type": "PAN",
                "document_id": str(doc.id), "field": "pan",
                "page": number_field.page if number_field else None,
                "confidence": number_field.confidence if number_field else None,
                "method": "KEY_FORMATS",
            }
        if doc_type == "OEM_AUTHORIZATION" and "statement" in block:
            # present ONLY when the letter's statement itself extracted —
            # an uploaded-but-unreadable letter stays missing -> NOT_VERIFIED
            statement = next((f for f in doc.extracted_fields
                              if f.field_name == "authorization_statement"), None)
            block["present"] = True
            refs["authorization.present"] = {
                "origin": "derived", "doc_type": "OEM_AUTHORIZATION",
                "document_id": str(doc.id), "field": "authorization_statement",
                "page": statement.page if statement else None,
                "confidence": statement.confidence if statement else None,
                "method": "statement_extracted",
            }
        if block:
            ev[root] = block

    # bidder-level numerics from Phase 6.7 documents (latest upload wins)
    for doc_type, field_name, out_key in _BIDDER_NUMERIC_FIELDS:
        doc = latest.get(doc_type)
        if doc is None:
            continue
        extracted = next((f for f in doc.extracted_fields
                          if f.field_name == field_name), None)
        number = _number(extracted.value) if extracted is not None else None
        if number is None:
            continue
        ev["bidder"][out_key] = number
        refs[f"bidder.{out_key}"] = {
            "origin": "document", "doc_type": doc_type,
            "document_id": str(doc.id), "field": field_name,
            "page": extracted.page, "confidence": extracted.confidence,
        }

    _verify_via_adapters(db, bidder, ev, refs)
    ev["_refs"] = refs
    return ev


def _tender_dict(tender: Tender) -> dict:
    # Numeric columns arrive as Decimal: convert once so every downstream
    # consumer (comparisons, evidence refs, stored JSONB profile) sees floats.
    out = {}
    for c in Tender.__table__.columns:
        if c.name in ("id", "created_at", "updated_at"):
            continue
        value = getattr(tender, c.name)
        out[c.name] = float(value) if isinstance(value, Decimal) else value
    return out


def _entity_result(cfg_rule: dict, stored: dict | None) -> dict:
    """ENTITY-CONSISTENCY-001: Phase 4's stored comparison, never recomputed."""
    if not stored:
        verdict, refs = VERDICT_NV, []
    else:
        stored_verdict = stored.get("verdict")
        if stored_verdict == "MATCH":
            verdict = cfg_rule["pass"]
        elif stored_verdict == "CONFLICT":
            verdict = cfg_rule["fail"]
        elif stored_verdict in (VERDICT_NV, VERDICT_NA):
            verdict = stored_verdict
        else:
            verdict = VERDICT_NV
        refs = [{"path": f"{r['source'].lower()}.legal_name", "origin": "document",
                 "doc_type": r["source"], "document_id": r["document_id"],
                 "field": r["field"], "page": r.get("page")}
                for r in stored.get("page_refs", [])]
        if refs:
            refs = [dict(r, origin="stored") for r in refs]
    return {"rule_id": cfg_rule["rule_id"], "verdict": verdict,
            "evidence_refs": refs, "source": _source_summary(refs),
            "legal_citation": cfg_rule.get("source")}


def _critical_override_fired(results: list[dict], critical_ids) -> bool:
    """Step 3 of Phase 5: flag only — risk scoring is Phase 6's job."""
    critical = set(critical_ids)
    return any(r["rule_id"] in critical and r["verdict"] in FAILURE_VERDICTS
               for r in results)


# --- Phase 6: score, risk, recommendation (all read rules_config.json) ------

def calculate_score(rule_results: list[dict]) -> dict:
    """scoring.weights + scoring.formula straight from the config.

    NOT_APPLICABLE -> 'excluded_from_denominator' -> out of numerator AND
    denominator. Everything-not-applicable -> score null + manual_review
    flag (never divide by zero, never fake a 100)."""
    weights = load_config()["scoring"]["weights"]
    evaluated, excluded = [], 0
    for result in rule_results:
        weight = weights[result["verdict"]]
        if weight == "excluded_from_denominator":
            excluded += 1
        elif not isinstance(weight, (int, float)) or isinstance(weight, bool):
            logger.error("non-numeric weight for verdict %s in scoring config",
                         result["verdict"])
            excluded += 1
        else:
            evaluated.append(weight)
    if not evaluated:
        return {"score": None, "evaluated": 0, "excluded": excluded,
                "manual_review": True}
    return {"score": round(100 * sum(evaluated) / len(evaluated)),
            "evaluated": len(evaluated), "excluded": excluded,
            "manual_review": False}


# config prose -> parseable boolean (thresholds/bands stay in the JSON)
_BAND_TRANSLATIONS = (
    (re.compile(r"\bno\s+([A-Za-z_]+)\s+triggered\b", re.I), r"\1 == false"),
    (re.compile(r"\bany\s+([A-Za-z_]+)\s+rule\s+fired\b", re.I), r"\1 == true"),
)


def calculate_risk(score, critical_override_fired: bool) -> str:
    """scoring.risk_bands evaluated in config order, first match wins.
    critical_override_fired winning over a high score is the HIGH band's
    own config text ('score < 60 OR any critical_override rule fired')."""
    if score is None:
        return "MEDIUM"   # unscorable (all NA): bands need a number; human looks
    bands = load_config()["scoring"]["risk_bands"]
    evidence = {"bidder": {"score": score, "critical_override": bool(critical_override_fired)}}
    for band_name, band_text in bands.items():
        expression = band_text
        for pattern, replacement in _BAND_TRANSLATIONS:
            expression = pattern.sub(replacement, expression)
        if _eval_truth(parse_condition(expression), evidence, {}, {}) is True:
            return band_name
    logger.error("no risk band matched score=%s critical_override=%s",
                 score, critical_override_fired)
    return "MEDIUM"


def generate_recommendation(rule_results: list[dict], score, risk: str) -> str:
    """Template sentence built from the actual verdicts + config requirement
    texts. Never an LLM call: the rule engine's output is already fixed."""
    rules = {r["rule_id"]: r for r in load_config()["rules"]}

    def requirement_text(rule_id: str) -> str:
        rule = rules.get(rule_id)
        return rule["requirement"] if rule else rule_id

    satisfied_cats: list[str] = []
    for result in rule_results:
        if result["verdict"] == "SATISFIED":
            rule = rules.get(result["rule_id"], {})
            category = rule.get("category", result["rule_id"])
            if category not in satisfied_cats:
                satisfied_cats.append(category)

    sentences: list[str] = []
    if satisfied_cats:
        names = ", ".join(satisfied_cats[:-1])
        if len(satisfied_cats) > 1:
            names += " and "
        sentences.append(f"Bidder satisfies {names}{satisfied_cats[-1]} requirements.")

    for result in rule_results:
        if result["verdict"] in ("CONFLICT", "VIOLATION"):
            sentences.append(f"{result['verdict']}: "
                             f"{requirement_text(result['rule_id'])} "
                             f"({result['rule_id']}).")

    for result in rule_results:
        if result["verdict"] == "NOT_VERIFIED":
            unconfirmed = [r["path"] for r in result["evidence_refs"]
                           if r.get("missing") or r.get("origin") == "unresolved"]
            sources = ", ".join(unconfirmed) or "evidence pending"
            sentences.append(f"NOT VERIFIED: {requirement_text(result['rule_id'])} "
                             f"({result['rule_id']}) — unconfirmed source: {sources}.")

    if score is None:
        sentences.append("Recommendation: MANUAL REVIEW REQUIRED — no scorable "
                         "requirements on this tender.")
    elif risk in ("MEDIUM", "HIGH"):
        sentences.append("Recommendation: MANUAL REVIEW REQUIRED before qualification.")
    else:
        sentences.append("Recommendation: no manual review indicated; "
                         "officer decision pending.")
    return " ".join(sentences)


def evaluate_bidder(bidder_id, tender_id) -> dict:
    """Full compliance profile: {rule_results, score, risk,
    critical_override_fired, recommendation, manual_review} — Phase 7 stores
    this object and the dashboard reads it as-is (no frontend recompute)."""
    config = load_config()
    rules = {r["rule_id"]: r for r in config["rules"]}

    with Session(engine) as db:
        bidder = db.get(Bidder, bidder_id)
        tender = db.get(Tender, tender_id)
        if bidder is None:
            raise ValueError(f"bidder {bidder_id} not found")
        if tender is None:
            raise ValueError(f"tender {tender_id} not found")

        requirements = (db.query(Requirement)
                        .filter(Requirement.tender_id == tender.id)
                        .order_by(Requirement.requirement_id)
                        .all())
        ev = build_bidder_evidence(db, bidder)
        stored_identity = (bidder.summary or {}).get("entity_consistency")
        tender_ev = _tender_dict(tender)

        results = []
        for requirement in requirements:
            cfg_rule = rules.get(requirement.rule_id)
            if cfg_rule is None:
                logger.error("rule_id %s not in rules_config.json", requirement.rule_id)
                results.append({"rule_id": requirement.rule_id,
                                "verdict": VERDICT_NV, "evidence_refs": [],
                                "source": ["missing_rule_config"],
                                "legal_citation": None})
                continue
            if cfg_rule["rule_id"] == "ENTITY-CONSISTENCY-001":
                results.append(_entity_result(cfg_rule, stored_identity))
            else:
                results.append(evaluate_rule(cfg_rule, ev, tender_ev))

        fired = _critical_override_fired(results, config.get("critical_override_rule_ids", []))
        score = calculate_score(results)["score"]
        risk = calculate_risk(score, fired)
        recommendation = generate_recommendation(results, score, risk)

        profile = {"bidder_id": str(bidder_id), "tender_id": str(tender_id),
                   "rule_results": results,
                   "score": score,
                   "risk": risk,
                   "critical_override_fired": fired,
                   "recommendation": recommendation,
                   "manual_review": risk in ("MEDIUM", "HIGH")}

        # Phase 7: store the submission record the dashboard reads.
        # Re-evaluation replaces it — one RuleResult set per bidder, ever.
        db.query(RuleResult).filter(RuleResult.bidder_id == bidder.id).delete(
            synchronize_session=False)
        for requirement, result in zip(requirements, results, strict=True):
            db.add(RuleResult(
                bidder_id=bidder.id, requirement_id=requirement.id,
                rule_id=result["rule_id"], verdict=result["verdict"],
                evidence=result["evidence_refs"],
            ))
        summary = dict(bidder.summary or {})
        summary["profile"] = profile
        summary["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        bidder.summary = summary

        counts: dict[str, int] = {}
        for result in results:
            counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
        audit(db, "RULES_EVALUATED", tender_id=tender.id, bidder_id=bidder.id,
              detail={"rules": len(results), "score": score, "risk": risk,
                      "critical_override_fired": fired, "verdicts": counts})
        failures = [r["rule_id"] for r in results if r["verdict"] in FAILURE_VERDICTS]
        if failures:
            audit(db, "CONFLICT_DETECTED", tender_id=tender.id, bidder_id=bidder.id,
                  detail={"rule_ids": failures, "score": score, "risk": risk})
        db.commit()

    logger.info("evaluate_bidder bidder=%s requirements=%s score=%s risk=%s "
                "critical_override_fired=%s",
                bidder_id, len(results), score, risk, fired)
    return profile
