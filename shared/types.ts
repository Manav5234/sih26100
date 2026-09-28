// SIH26100 — Shared TypeScript types
// One-to-one with backend Pydantic schemas / rules_config.json. Field names
// match the API JSON keys.

// ---- Enums ----

export type Verdict =
  | "SATISFIED"
  | "VIOLATION"
  | "NOT_VERIFIED"
  | "CONFLICT"
  | "NOT_APPLICABLE";

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";

export type DecisionType = "APPROVE" | "REJECT" | "SEND_FOR_CLARIFICATION";

export type DocumentType =
  | "TENDER"
  | "PAN"
  | "GST"
  | "UDYAM"
  | "FINANCIAL"
  | "OEM_AUTHORIZATION"
  | "LOCAL_CONTENT"
  | "OTHER";

export type DocumentStatus =
  | "UPLOADED"
  | "TEXT_EXTRACTED"
  | "OCR_EXTRACTED"
  | "UNREADABLE"
  | "FAILED";

export type OfficerRole = "ADMIN" | "INSPECTOR" | "VIEWER";

// ---- Tender ----

export interface TenderFields {
  minimum_turnover: number | null;
  required_msme_tier: string[] | null;
  local_content_requirement_applicable: boolean;
  // exactly the LOCAL-CONTENT-001 class_order values rules_config.json compares against
  required_local_content_class:
    | "class_1_local_supplier"
    | "class_2_local_supplier"
    | "non_local"
    | null;
  bid_value_cr: number | null;
  required_oem: string | null;
}

export interface Requirement {
  id: string;
  tender_id: string;
  requirement_id: string; // REQ-001
  title: string;
  category: string;
  source_clause: string | null;
  required_evidence: string[];
  rule_id: string;
  status: string; // PENDING | ...
}

// Rule definition as read from rules_config.json (joined onto requirements
// by the API so the UI can show the legal source next to the clause).
export interface RuleDefinition {
  rule_id: string;
  requirement: string;
  category: string;
  source: string;
  condition: string | Record<string, string>;
  pass: Verdict;
  fail: Verdict;
  on_source_unreachable?: Verdict;
  not_applicable_when?: string;
  tender_override_allowed: boolean;
  critical_override?: boolean;
  notes?: string;
  warning?: string;
}

export interface RequirementWithRule extends Requirement {
  // rules_config.json join served by GET /tenders/{id}/requirements and
  // POST /tenders/upload — requirement text + legal source + config date
  rule: RuleJoin | null;
}

export interface RuleJoin {
  rule_id: string;
  requirement: string | null;
  source: string | null;
  last_verified: string | null;
}
