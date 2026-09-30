import { getApiUrl } from "./config";

/**
 * Standardized typed API client for SIH26100 frontend.
 * Consolidates base URL resolution, bearer token authentication, JSON parsing,
 * and unified error handling across all pages.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthOfficer {
  id: string;
  role: string;
}

export interface AuthLoginResponse {
  token: string;
  officer: AuthOfficer;
}

export interface DashboardEntry {
  bidder_id: string;
  name: string;
  tender_id: string;
  tender_ref: string;
  score: number | null;
  risk: string | null;
  status: string;
  pending_review: boolean;
  recommendation: string | null;
  evaluated_at: string | null;
}

export interface DashboardResponse {
  bidders: DashboardEntry[];
  count: number;
}

export interface TenderOut {
  id: string;
  tender_ref: string;
  title: string;
  created_at: string;
  requirement_count: number;
  required_oem?: string | null;
  required_local_content_class?: string | null;
  minimum_turnover?: number | null;
  bid_value_cr?: number | null;
  local_content_requirement_applicable?: boolean;
}

export interface TenderListResponse {
  tenders: TenderOut[];
  count: number;
}

export interface RuleJoin {
  rule_id: string;
  requirement: string | null;
  source: string | null;
  description?: string | null;
  last_verified: string | null;
}

export interface RequirementOut {
  id: string;
  tender_id: string;
  requirement_id: string;
  title: string;
  category: string;
  source_clause: string | null;
  required_evidence: string[];
  rule_id: string;
  status: string;
  rule: RuleJoin | null;
}

export interface RequirementListResponse {
  tender_id: string;
  tender_ref: string;
  requirements: RequirementOut[];
}

export interface TenderDetailOut extends TenderOut {
  extraction_method: "llm" | "template_fallback" | string;
  requirements: RequirementOut[];
}

export interface BidderOut {
  id: string;
  tender_id: string;
  name: string;
  legal_name: string | null;
}

export interface Decision {
  id: string;
  bidder_id?: string;
  decision: string;
  reason: string | null;
  officer_name: string | null;
  created_at: string;
}

export interface EntityConsistency {
  verdict: string | null;
  names: Record<string, { name: string | null; normalized: string | null }>;
  outliers: string[];
  missing: string[];
}

export interface EvidenceRef {
  path?: string | null;
  document_filename?: string | null;
  doc_type?: string | null;
  document_id?: string | null;
  page?: number | null;
  value?: string | null;
  confidence?: number | null;
  source?: string | null;
  origin?: string | null;
  field?: string | null;
  [key: string]: unknown;
}

export interface RuleResult {
  rule_id: string;
  requirement: string | null;
  verdict: string;
  legal_citation: string | null;
  source: string[];
  evidence_refs: EvidenceRef[];
  entity_consistency: EntityConsistency | null;
}

export interface ComplianceProfile {
  bidder_id: string;
  tender_id: string;
  tender_ref: string | null;
  score: number | null;
  risk: string | null;
  critical_override_fired: boolean;
  recommendation: string | null;
  manual_review: boolean;
  evaluated_at: string | null;
  rule_results: RuleResult[];
  decision: Decision | null;
  demo_notice: string;
}

export interface ComplianceReport {
  report_type: string;
  demo_notice: string;
  advisory_notice: string;
  tender: {
    id: string;
    tender_ref: string | null;
    title: string | null;
  };
  bidder: {
    id: string;
    name: string;
    legal_name: string | null;
  };
  evaluation: {
    score: number | null;
    risk: string | null;
    critical_override_fired: boolean;
    manual_review: boolean;
    evaluated_at: string | null;
    rule_count: number;
  };
  system_recommendation: {
    label: string;
    text: string | null;
  };
  officer_decision: {
    label: string;
    latest: {
      id: string;
      decision: string;
      reason: string;
      officer_name: string | null;
      recorded_at: string;
    } | null;
    history: Array<{
      id: string;
      decision: string;
      reason: string;
      officer_name: string | null;
      recorded_at: string;
    }>;
  };
  rule_results: Array<{
    rule_id: string;
    requirement: string | null;
    category: string | null;
    verdict: string;
    legal_citation: string | null;
    evidence_refs: EvidenceRef[];
    entity_consistency: EntityConsistency | null;
  }>;
  identity_consistency: Record<string, unknown> | null;
  generated_at: string;
}

export interface AuditEvent {
  stage: string;
  detail: Record<string, unknown>;
  timestamp: string;
  bidder_id?: string | null;
  tender_id?: string | null;
  actor?: string | null;
}

export interface BidderAuditResponse {
  bidder_id: string;
  tender_id: string;
  events: AuditEvent[];
}

export interface DocumentField {
  field_name: string;
  value: string | null;
  confidence: number | null;
  page: number | null;
  extraction_method: string | null;
}

export interface DocumentOut {
  id?: string;
  doc_type: string;
  status: string;
  file_path?: string | null;
  uploaded_at?: string | null;
  extraction_method?: string | null;
  fields: DocumentField[];
}

export interface DocumentListResponse {
  bidder_id: string;
  documents: DocumentOut[];
}

// ---------------------------------------------------------------------------
// Token & Core Fetch Client
// ---------------------------------------------------------------------------

export async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  try {
    const res = await fetch("/api/auth/token", { cache: "no-store" });
    if (!res.ok) return null;
    const data = (await res.json()) as { token?: string | null };
    return data.token || null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const baseUrl = getApiUrl();
  const url = path.startsWith("http") ? path : `${baseUrl}${path}`;

  const headers = new Headers(options.headers || {});

  // Automatically attach Bearer token if not explicitly provided
  if (!headers.has("Authorization")) {
    const token = await getAuthToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  // If body is JSON string and content-type not set, set it
  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers,
    });
  } catch {
    throw new ApiError(
      0,
      `Unable to reach the compliance backend at ${baseUrl}. Please verify the service is running.`
    );
  }

  if (!res.ok) {
    let errorDetail = `Request failed (HTTP ${res.status})`;
    try {
      const errorJson = await res.json();
      if (errorJson && typeof errorJson.detail === "string") {
        errorDetail = errorJson.detail;
      } else if (errorJson && typeof errorJson.error === "string") {
        errorDetail = errorJson.error;
      }
    } catch {
      // Not JSON body
    }

    if (res.status === 401) {
      errorDetail = "Authentication required. Please sign in to perform this action.";
    } else if (res.status === 403) {
      errorDetail = "Insufficient permissions for this operation.";
    }

    throw new ApiError(res.status, errorDetail);
  }

  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// API Methods
// ---------------------------------------------------------------------------

export const api = {
  // Dashboard
  getDashboard: () => apiFetch<DashboardResponse>("/dashboard"),

  // Tenders
  getTenders: () => apiFetch<TenderListResponse>("/tenders"),
  getTenderRequirements: (tenderId: string) =>
    apiFetch<RequirementListResponse>(`/tenders/${tenderId}/requirements`),
  uploadTender: (formData: FormData) =>
    apiFetch<TenderDetailOut>("/tenders/upload", {
      method: "POST",
      body: formData,
    }),

  // Bidders
  createBidder: (data: { name: string; legal_name?: string; tender_id: string }) =>
    apiFetch<BidderOut>("/bidders", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getBidderProfile: async (bidderId: string): Promise<ComplianceProfile | null> => {
    try {
      return await apiFetch<ComplianceProfile>(`/bidders/${bidderId}/profile`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        return null;
      }
      throw err;
    }
  },
  getBidderAudit: (bidderId: string) =>
    apiFetch<BidderAuditResponse>(`/bidders/${bidderId}/audit`),
  getBidderDocuments: (bidderId: string) =>
    apiFetch<DocumentListResponse>(`/bidders/${bidderId}/documents`),
  uploadBidderDocument: (bidderId: string, formData: FormData) =>
    apiFetch<DocumentOut>(`/bidders/${bidderId}/documents`, {
      method: "POST",
      body: formData,
    }),
  verifyIdentity: (bidderId: string) =>
    apiFetch<EntityConsistency>(`/bidders/${bidderId}/verify-identity`, {
      method: "POST",
    }),
  evaluateBidder: (bidderId: string) =>
    apiFetch<Record<string, unknown>>(`/bidders/${bidderId}/evaluate`, {
      method: "POST",
    }),
  recordDecision: (bidderId: string, decision: string, reason: string) =>
    apiFetch<Decision>(`/bidders/${bidderId}/decisions`, {
      method: "POST",
      body: JSON.stringify({ decision, reason }),
    }),

  // Reports
  getBidderReport: (bidderId: string) =>
    apiFetch<ComplianceReport>(`/bidders/${bidderId}/report`),

  // Requirements Update
  updateRequirement: (
    tenderId: string,
    requirementId: string,
    body: { title?: string; source_clause?: string; required_evidence?: string[]; category?: string }
  ) =>
    apiFetch<RequirementOut>(`/tenders/${tenderId}/requirements/${requirementId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  // Global Audit
  getGlobalAudit: (params?: {
    tender_id?: string;
    bidder_id?: string;
    event_type?: string;
    limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.tender_id) sp.set("tender_id", params.tender_id);
    if (params?.bidder_id) sp.set("bidder_id", params.bidder_id);
    if (params?.event_type) sp.set("event_type", params.event_type);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString();
    return apiFetch<{ events: AuditEvent[]; count: number }>(`/audit${qs ? `?${qs}` : ""}`);
  },

  // Filtered Bidders List
  listBidders: (params?: {
    tender_id?: string;
    risk?: string;
    status?: string;
    search?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.tender_id) sp.set("tender_id", params.tender_id);
    if (params?.risk) sp.set("risk", params.risk);
    if (params?.status) sp.set("status", params.status);
    if (params?.search) sp.set("search", params.search);
    const qs = sp.toString();
    return apiFetch<{ bidders: DashboardEntry[]; count: number }>(`/bidders${qs ? `?${qs}` : ""}`);
  },

  // Health
  checkHealth: async (): Promise<{
    status: "healthy" | "unreachable";
    service?: string;
    latencyMs?: number;
  }> => {
    const start = performance.now();
    try {
      const res = await fetch(`${getApiUrl()}/health`, { cache: "no-store" });
      const duration = Math.round(performance.now() - start);
      if (res.ok) {
        const data = await res.json();
        return {
          status: "healthy",
          service: data.service || "sih26100-backend",
          latencyMs: duration,
        };
      }
      return { status: "unreachable", latencyMs: duration };
    } catch {
      return { status: "unreachable" };
    }
  },
};
