"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  ComplianceProfile,
  RuleResult,
  DocumentOut,
  AuditEvent,
  DashboardEntry,
} from "@/lib/api";
import { AppShell } from "@/components/layout/AppShell";
import { ComplianceBadge, DecisionStatusBadge, RiskBadge } from "@/components/ui/Badges";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { Modal } from "@/components/ui/Modal";
import { StatCard } from "@/components/ui/StatCard";
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconHistory,
  IconShield,
  IconUpload,
  IconRefresh,
  IconCheckCircle,
  IconXCircle,
  IconInfo,
  IconUsers,
} from "@/components/ui/Icons";

// ──────────────────────────────────────────────────────────────────────────────
// Document Configuration
// ──────────────────────────────────────────────────────────────────────────────

const DOC_TYPES = [
  "PAN",
  "GST",
  "UDYAM",
  "FINANCIAL",
  "OEM_AUTHORIZATION",
  "LOCAL_CONTENT",
];

const DOC_LABELS: Record<string, string> = {
  PAN: "PAN Certificate",
  GST: "GST Registration",
  UDYAM: "Udyam Certificate",
  FINANCIAL: "Financial / Turnover",
  OEM_AUTHORIZATION: "OEM Authorization",
  OEM_AUTH: "OEM Authorization",
  LOCAL_CONTENT: "Local Content Declaration",
};

function verdictCounts(results: RuleResult[]) {
  const c = {
    SATISFIED: 0,
    VIOLATION: 0,
    CONFLICT: 0,
    NOT_VERIFIED: 0,
    NOT_APPLICABLE: 0,
  };
  for (const r of results) {
    const k = r.verdict as keyof typeof c;
    if (k in c) c[k]++;
  }
  return c;
}

// ──────────────────────────────────────────────────────────────────────────────
// Main page component
// ──────────────────────────────────────────────────────────────────────────────

export default function BidderCompliancePage() {
  const params = useParams<{ id: string }>();
  const bidderId = params?.id;

  const [profile, setProfile] = useState<ComplianceProfile | null>(null);
  const [profileMissing, setProfileMissing] = useState(false);
  const [bidderEntry, setBidderEntry] = useState<DashboardEntry | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [drawerRule, setDrawerRule] = useState<RuleResult | null>(null);
  const [verdictFilter, setVerdictFilter] = useState("ALL");

  // Document upload state
  const [uploadingDoc, setUploadingDoc] = useState<string | null>(null);
  const [uploadDocError, setUploadDocError] = useState("");
  const [identityBusy, setIdentityBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const currentDocType = useRef<string>("");

  // Confirm decision dialog state
  const [confirmDecision, setConfirmDecision] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!bidderId) return;
    try {
      const [profData, auditData, docData, dashData] = await Promise.all([
        api.getBidderProfile(bidderId),
        api.getBidderAudit(bidderId).catch(() => ({ bidder_id: bidderId, tender_id: "", events: [] })),
        api.getBidderDocuments(bidderId).catch(() => ({ bidder_id: bidderId, documents: [] })),
        api.getDashboard().catch(() => ({ bidders: [], count: 0 })),
      ]);

      setProfile(profData);
      setProfileMissing(profData === null);
      setEvents(auditData.events || []);
      setDocuments(docData.documents || []);

      const found = (dashData.bidders || []).find((b) => b.bidder_id === bidderId);
      if (found) setBidderEntry(found);
      setError("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load bidder profile. Please retry."
      );
    }
  }, [bidderId]);

  useEffect(() => {
    if (bidderId) {
      load();
    }
  }, [bidderId, load]);


  // ── Evaluate ─────────────────────────────────────────────────────────────────

  async function runEvaluation() {
    if (!bidderId) return;
    setBusy(true);
    setError("");
    setSuccessMessage("");
    try {
      await api.evaluateBidder(bidderId);
      setSuccessMessage("Rule evaluation completed successfully.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setBusy(false);
    }
  }

  // ── Identity verify ───────────────────────────────────────────────────────────

  async function runIdentityVerify() {
    if (!bidderId) return;
    setIdentityBusy(true);
    setError("");
    setSuccessMessage("");
    try {
      await api.verifyIdentity(bidderId);
      setSuccessMessage("Identity verification completed.");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Identity check failed");
    } finally {
      setIdentityBusy(false);
    }
  }

  // ── Document upload ───────────────────────────────────────────────────────────

  function triggerDocUpload(docType: string) {
    currentDocType.current = docType;
    setUploadDocError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
      fileInputRef.current.click();
    }
  }

  async function handleDocFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !bidderId) return;
    if (file.type !== "application/pdf") {
      setUploadDocError("Only PDF files are accepted.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadDocError("File too large (max 10 MB).");
      return;
    }
    const dt = currentDocType.current;
    setUploadingDoc(dt);
    setUploadDocError("");
    try {
      const form = new FormData();
      form.append("doc_type", dt);
      form.append("file", file);
      await api.uploadBidderDocument(bidderId, form);
      setSuccessMessage(`Uploaded and extracted ${DOC_LABELS[dt] || dt} successfully.`);
      await load();
    } catch (err) {
      setUploadDocError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploadingDoc(null);
    }
  }

  // ── Officer decision ──────────────────────────────────────────────────────────

  async function recordDecision(decision: string) {
    if (!bidderId) return;
    if (!reason.trim()) {
      setError("A reason is required for every officer decision.");
      return;
    }
    setConfirmDecision(null);
    setBusy(true);
    setError("");
    setSuccessMessage("");
    try {
      await api.recordDecision(bidderId, decision, reason.trim());
      setSuccessMessage(`Officer decision (${decision}) recorded successfully and logged to the audit trail.`);
      setReason("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision recording failed");
    } finally {
      setBusy(false);
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────────

  const name = bidderEntry?.name || "Bidder Compliance";
  const counts = profile ? verdictCounts(profile.rule_results) : null;
  const filteredResults = (profile?.rule_results || []).filter((r) =>
    verdictFilter === "ALL" ? true : r.verdict === verdictFilter
  );
  const docByType = Object.fromEntries(
    (documents || []).map((d) => [d.doc_type, d])
  );

  return (
    <AppShell officerName={name || "Officer"}>
      {/* Hidden file input for document upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={handleDocFileSelect}
      />

      <div className="space-y-6">
        {/* Breadcrumb + title */}
        <div>
          <Link
            href="/bidders"
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <IconArrowLeft className="h-3.5 w-3.5" />
            <span>All Bidders</span>
          </Link>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
                {name}
              </h1>
              {profile && (
                <DecisionStatusBadge
                  status={
                    profile.decision
                      ? profile.decision.decision
                      : "AWAITING_DECISION"
                  }
                />
              )}
              {bidderEntry && <RiskBadge risk={bidderEntry.risk} />}
            </div>
            {profile && (
              <Link
                href="/reports"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50 shadow-2xs transition-colors"
              >
                <span>Official Report &amp; Dossier →</span>
              </Link>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {profile?.tender_ref ? `Tender ${profile.tender_ref} — ` : ""}
            Compliance workspace: documents, evidence, verification, officer decision.
          </p>
        </div>

        <DemoNotice />

        {/* Success banner */}
        {successMessage && (
          <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800">
            <IconCheckCircle className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Success</p>
              <p className="mt-0.5 text-emerald-700">{successMessage}</p>
            </div>
            <button
              onClick={() => setSuccessMessage("")}
              className="font-semibold text-emerald-700 hover:text-emerald-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Action failed</p>
              <p className="mt-0.5 text-rose-700">{error}</p>
            </div>
            <button
              onClick={() => setError("")}
              className="font-semibold text-rose-700 hover:text-rose-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Upload error banner */}
        {uploadDocError && (
          <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-amber-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Document upload failed</p>
              <p className="mt-0.5">{uploadDocError}</p>
            </div>
            <button
              onClick={() => setUploadDocError("")}
              className="font-semibold text-amber-700 hover:text-amber-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* ─── SECTION 1: Documents ──────────────────────────────────────────── */}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Bidder Documents
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={load}
                className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-700 transition-colors"
              >
                <IconRefresh className="h-3.5 w-3.5" />
                Refresh
              </button>
            </div>
          </div>
          <div className="divide-y divide-slate-100">
            {DOC_TYPES.map((dt) => {
              const doc = docByType[dt];
              const isUploading = uploadingDoc === dt;
              const status = doc?.status ?? "missing";
              return (
                <div key={dt} className="flex items-center gap-4 px-4 py-3">
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
                      status === "present"
                        ? "bg-emerald-50 border-emerald-200"
                        : status === "unreadable"
                        ? "bg-rose-50 border-rose-200"
                        : status === "pending"
                        ? "bg-amber-50 border-amber-200"
                        : "bg-slate-100 border-slate-200"
                    }`}
                  >
                    {status === "present" ? (
                      <IconCheckCircle className="h-4 w-4 text-emerald-600" />
                    ) : status === "unreadable" ? (
                      <IconXCircle className="h-4 w-4 text-rose-500" />
                    ) : status === "pending" ? (
                      <span className="h-3 w-3 rounded-full border-2 border-amber-500 border-t-transparent animate-spin" />
                    ) : (
                      <IconInfo className="h-4 w-4 text-slate-400" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-800">
                      {DOC_LABELS[dt] || dt}
                    </p>
                    {doc && doc.fields.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
                        {doc.fields.slice(0, 3).map((f) => (
                          <span
                            key={f.field_name}
                            className="text-[11px] text-slate-500"
                          >
                            <span className="font-semibold">{f.field_name}:</span>{" "}
                            {f.value ?? "—"}
                            {f.confidence != null &&
                              ` (${Math.round(f.confidence * 100)}%)`}
                          </span>
                        ))}
                      </div>
                    )}
                    {doc?.extraction_method && (
                      <span className="mt-0.5 inline-block text-[10px] font-mono text-slate-400">
                        {doc.extraction_method} extraction
                      </span>
                    )}
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase border ${
                        status === "present"
                          ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                          : status === "unreadable"
                          ? "bg-rose-50 border-rose-200 text-rose-700"
                          : status === "pending"
                          ? "bg-amber-50 border-amber-200 text-amber-700"
                          : "bg-slate-100 border-slate-200 text-slate-500"
                      }`}
                    >
                      {status}
                    </span>
                    <button
                      onClick={() => triggerDocUpload(dt)}
                      disabled={isUploading}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                    >
                      {isUploading ? (
                        <span className="h-3 w-3 rounded-full border-2 border-slate-400 border-t-transparent animate-spin" />
                      ) : (
                        <IconUpload className="h-3.5 w-3.5" />
                      )}
                      {isUploading ? "Extracting…" : "Upload"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ─── SECTION 2: Identity Verification ──────────────────────────────── */}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Entity Identity Verification
              </p>
              <p className="mt-0.5 text-[11px] text-slate-400">
                Cross-checks PAN, GST, and Udyam entity names for consistency.
              </p>
            </div>
            <button
              onClick={runIdentityVerify}
              disabled={identityBusy}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors"
            >
              {identityBusy ? (
                <span className="h-3.5 w-3.5 rounded-full border-2 border-slate-400 border-t-transparent animate-spin" />
              ) : (
                <IconUsers className="h-3.5 w-3.5" />
              )}
              {identityBusy ? "Checking…" : "Run Identity Check"}
            </button>
          </div>
          {(() => {
            const entityResult = profile?.rule_results?.find(
              (r) => r.rule_id === "ENTITY-CONSISTENCY-001"
            );
            const ec = entityResult?.entity_consistency;
            if (!ec) {
              return (
                <div className="px-4 py-6 text-sm text-slate-400 text-center">
                  No identity check run yet. Upload PAN, GST, and Udyam documents, then run identity check.
                </div>
              );
            }
            return (
              <div className="p-4 space-y-3">
                <div className="flex items-center gap-3">
                  <ComplianceBadge
                    status={ec.verdict || "NOT_VERIFIED"}
                    size="lg"
                  />
                  {ec.verdict === "CONFLICT" && (
                    <span className="text-sm font-bold text-rose-700">
                      ⚠ Conflict detected — manual officer review required
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {Object.entries(ec.names).map(([src, n]) => {
                    const isOutlier = ec.outliers?.includes(src);
                    return (
                      <div
                        key={src}
                        className={`rounded-xl border p-3 ${
                          isOutlier
                            ? "border-rose-200 bg-rose-50"
                            : ec.missing?.includes(src)
                            ? "border-amber-200 bg-amber-50"
                            : "border-slate-200 bg-slate-50"
                        }`}
                      >
                        <p
                          className={`text-[10px] font-black uppercase tracking-wider mb-1 ${
                            isOutlier ? "text-rose-600" : "text-slate-500"
                          }`}
                        >
                          {src}
                          {isOutlier && " ← OUTLIER"}
                        </p>
                        <p
                          className={`text-sm font-semibold ${
                            isOutlier ? "text-rose-800" : "text-slate-800"
                          }`}
                        >
                          {n.name || "—"}
                        </p>
                        {n.normalized && n.normalized !== n.name && (
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            Normalized: {n.normalized}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
                {ec.outliers.length > 0 && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                    <strong>Conflict detected:</strong> The entity name in {ec.outliers.join(", ")} does not match the other documents. This triggers a critical override, setting risk to HIGH and routing the bidder to manual review.
                  </div>
                )}
                {ec.missing.length > 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    <strong>Missing evidence:</strong> {ec.missing.join(", ")} document not uploaded — verdict is NOT_VERIFIED, not VIOLATION.
                  </div>
                )}
              </div>
            );
          })()}
        </div>

        {/* ─── SECTION 3: Compliance Profile ─────────────────────────────────── */}
        {profileMissing && !error && (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-card">
            <IconShield className="mx-auto h-10 w-10 text-slate-300 mb-4" />
            <h2 className="text-base font-bold text-slate-800">
              No compliance profile yet
            </h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
              Upload bidder documents, run identity verification, then run the rule engine to produce score, risk and rule-by-rule verdicts.
            </p>
            <button
              onClick={runEvaluation}
              disabled={busy}
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {busy ? (
                <>
                  <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Evaluating…
                </>
              ) : (
                <>
                  <IconShield className="h-4 w-4" />
                  Run Rule Engine Evaluation
                </>
              )}
            </button>
          </div>
        )}

        {profile && (
          <>
            {/* Compliance score + KPI cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div
                className={`relative overflow-hidden rounded-2xl border p-5 shadow-card ${
                  profile.risk === "HIGH"
                    ? "border-rose-200 bg-gradient-to-br from-rose-50 to-white"
                    : profile.risk === "MEDIUM"
                    ? "border-amber-200 bg-gradient-to-br from-amber-50 to-white"
                    : "border-emerald-200 bg-gradient-to-br from-emerald-50 to-white"
                }`}
              >
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">
                  Compliance Score &amp; Risk
                </p>
                <div className="flex items-baseline gap-2">
                  <span className="text-5xl font-black text-slate-900">
                    {profile.score ?? "—"}
                  </span>
                  <span className="text-lg font-bold text-slate-400">/ 100</span>
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <RiskBadge risk={profile.risk} />
                  {profile.manual_review && (
                    <span className="inline-flex items-center rounded-md bg-amber-100 border border-amber-300 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                      MANUAL REVIEW REQUIRED
                    </span>
                  )}
                </div>
                {profile.critical_override_fired && (
                  <div className="mt-3 rounded-lg border border-rose-300 bg-rose-100/70 p-2.5 text-xs text-rose-900">
                    <p className="font-bold flex items-center gap-1">
                      <IconAlertTriangle className="h-3.5 w-3.5 text-rose-700 shrink-0" />
                      Critical Override Triggered
                    </p>
                    <p className="mt-1 text-[11px] leading-relaxed text-rose-800">
                      Even with a compliance score of {profile.score}/100, a critical rule condition (e.g. Entity Consistency Conflict or Debarment) supersedes the numerical score and enforces a HIGH risk rating.
                    </p>
                  </div>
                )}
              </div>
              <StatCard
                label="Verdict breakdown"
                value={`${counts?.SATISFIED ?? 0} / ${profile.rule_results.length}`}
                supportingText={`${counts?.VIOLATION ?? 0} violation · ${counts?.CONFLICT ?? 0} conflict · ${counts?.NOT_VERIFIED ?? 0} not verified`}
                tone="purple"
                icon={<IconShield className="h-5 w-5" />}
              />
              <StatCard
                label="Evaluated"
                value={
                  profile.evaluated_at
                    ? new Date(profile.evaluated_at).toLocaleTimeString("en-IN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—"
                }
                supportingText={
                  profile.evaluated_at
                    ? new Date(profile.evaluated_at).toLocaleDateString("en-IN", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                      })
                    : "Not yet evaluated"
                }
                tone="brand"
                icon={<IconHistory className="h-5 w-5" />}
              />
            </div>

            {/* System Recommendation */}
            {profile.recommendation && (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 shadow-card">
                <div className="flex items-center gap-2 mb-2">
                  <span className="inline-flex items-center rounded-md bg-amber-200 border border-amber-300 px-2.5 py-0.5 text-[10px] font-black uppercase tracking-wider text-amber-900">
                    System Recommendation
                  </span>
                  <span className="text-[11px] text-amber-700">
                    — Advisory only
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-amber-900 font-medium">
                  {profile.recommendation}
                </p>
                <p className="mt-2 text-[11px] text-amber-700">
                  This recommendation is derived deterministically from evaluated rule conditions. All qualification and disqualification decisions are strictly reserved for the Procurement Officer.
                </p>
              </div>
            )}

            {/* Rule Results */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
              <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex flex-wrap items-center gap-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mr-2">
                  Rule Results
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {[
                    "ALL",
                    "SATISFIED",
                    "VIOLATION",
                    "CONFLICT",
                    "NOT_VERIFIED",
                    "NOT_APPLICABLE",
                  ].map((v) => (
                    <button
                      key={v}
                      onClick={() => setVerdictFilter(v)}
                      className={`rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide border transition-colors ${
                        verdictFilter === v
                          ? "bg-brand-600 text-white border-brand-600"
                          : "border-slate-200 text-slate-500 bg-white hover:bg-slate-50"
                      }`}
                    >
                      {v === "ALL"
                        ? `All (${profile.rule_results.length})`
                        : `${v} (${counts?.[v as keyof typeof counts] ?? 0})`}
                    </button>
                  ))}
                </div>
                <div className="ml-auto">
                  <button
                    onClick={runEvaluation}
                    disabled={busy}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                  >
                    <IconRefresh className="h-3.5 w-3.5" />
                    {busy ? "Evaluating…" : "Re-evaluate"}
                  </button>
                </div>
              </div>
              <div className="divide-y divide-slate-100">
                {filteredResults.length === 0 && (
                  <p className="px-4 py-6 text-sm text-slate-400 text-center">
                    No results match the selected filter.
                  </p>
                )}
                {filteredResults.map((r) => (
                  <div
                    key={r.rule_id}
                    className="px-4 py-3 hover:bg-slate-50/50 transition-colors"
                  >
                    <div className="flex flex-wrap items-start gap-3">
                      <ComplianceBadge status={r.verdict} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-slate-800">
                          {r.requirement || r.rule_id}
                        </p>
                        <p className="mt-0.5 font-mono text-[11px] font-bold text-brand-700">
                          {r.rule_id}
                        </p>
                        {r.legal_citation && (
                          <p className="mt-1 text-xs leading-relaxed text-slate-500">
                            {r.legal_citation}
                          </p>
                        )}
                        {r.source.length > 0 && (
                          <p className="mt-1 text-[11px] text-slate-400">
                            Source: {r.source.join(", ")}
                          </p>
                        )}
                      </div>
                      <button
                        onClick={() => setDrawerRule(r)}
                        className="shrink-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
                      >
                        Evidence ({r.evidence_refs.length})
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Officer Decision Section */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
              <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Officer Decision
                </p>
                <p className="mt-0.5 text-[11px] text-slate-400">
                  The Procurement Officer is the sole authorized decision-maker. The system never records an approval or rejection automatically.
                </p>
              </div>
              <div className="p-5 space-y-4">
                {profile.decision ? (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <DecisionStatusBadge status={profile.decision.decision} />
                      <span className="text-sm font-semibold text-slate-800">
                        {profile.decision.officer_name || "Procurement Officer"}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(profile.decision.created_at).toLocaleString("en-IN")}
                      </span>
                    </div>
                    {profile.decision.reason && (
                      <p className="rounded-xl bg-white border border-slate-100 p-3 text-sm text-slate-700">
                        {profile.decision.reason}
                      </p>
                    )}
                    <p className="text-[11px] text-slate-400">
                      Recorded decision is persisted and permanently immutably logged in the audit trail.
                    </p>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 rounded-xl bg-slate-50 border border-slate-200 p-3">
                    No officer decision recorded yet. The advisory recommendation above is not a decision.
                  </p>
                )}

                <div>
                  <label
                    htmlFor="decision-reason"
                    className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5"
                  >
                    Officer Reasoning / Justification Notes
                  </label>
                  <textarea
                    id="decision-reason"
                    rows={3}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Enter compliance evaluation notes and officer justification. This will be stored alongside your identity and timestamp."
                    className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
                  />
                </div>

                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setConfirmDecision("APPROVE")}
                    disabled={busy || !reason.trim()}
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <IconCheckCircle className="h-4 w-4" />
                    Approve Bidder
                  </button>
                  <button
                    onClick={() => setConfirmDecision("SEND_FOR_CLARIFICATION")}
                    disabled={busy || !reason.trim()}
                    className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <IconAlertTriangle className="h-4 w-4" />
                    Send for Clarification
                  </button>
                  <button
                    onClick={() => setConfirmDecision("REJECT")}
                    disabled={busy || !reason.trim()}
                    className="inline-flex items-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <IconXCircle className="h-4 w-4" />
                    Reject Bidder
                  </button>
                </div>
                {!reason.trim() && (
                  <p className="text-[11px] text-slate-400">
                    ↑ Please specify an officer justification note before recording a decision.
                  </p>
                )}
              </div>
            </div>
          </>
        )}

        {/* Audit Trail */}
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Audit Trail
            </p>
            <p className="mt-0.5 text-[11px] text-slate-400">
              Chronological pipeline: tender upload → extraction → documents → identity → rules → decision.
            </p>
          </div>
          {events.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-400 text-center">
              No audit events yet.
            </p>
          ) : (
            <ol className="relative border-l border-slate-200 ml-6 my-4 space-y-0">
              {events.map((ev, i) => (
                <li
                  key={`${ev.stage}-${ev.timestamp}-${i}`}
                  className="ml-6 pb-4"
                >
                  <span
                    className={`absolute -left-3 flex h-6 w-6 items-center justify-center rounded-full border-2 text-white text-[9px] font-black ${
                      ev.stage === "OFFICER_DECISION_RECORDED"
                        ? "border-emerald-400 bg-emerald-500"
                        : ev.stage === "CONFLICT_DETECTED"
                        ? "border-rose-400 bg-rose-500"
                        : ev.stage === "ENTITY_CONSISTENCY_CHECK"
                        ? "border-purple-400 bg-purple-500"
                        : ev.stage === "RULES_EVALUATED"
                        ? "border-brand-400 bg-brand-500"
                        : "border-slate-300 bg-slate-400"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <div className="px-3 py-2 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-slate-50 transition-colors">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span
                        className={`font-mono text-xs font-bold ${
                          ev.stage === "OFFICER_DECISION_RECORDED"
                            ? "text-emerald-700"
                            : ev.stage === "CONFLICT_DETECTED"
                            ? "text-rose-700"
                            : ev.stage === "ENTITY_CONSISTENCY_CHECK"
                            ? "text-purple-700"
                            : "text-slate-700"
                        }`}
                      >
                        {ev.stage}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        {new Date(ev.timestamp).toLocaleString("en-IN")}
                      </span>
                    </div>
                    {Object.keys(ev.detail).length > 0 && (
                      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-0.5">
                        {Object.entries(ev.detail).map(([k, v]) => (
                          <div key={k} className="flex gap-2 text-xs">
                            <dt className="shrink-0 font-semibold text-slate-500">
                              {k}:
                            </dt>
                            <dd className="min-w-0 break-words text-slate-700">
                              {v === null || v === undefined ? "—" : String(v)}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {/* ─── Evidence Drawer ──────────────────────────────────────────────────── */}
      <Modal
        isOpen={drawerRule !== null}
        onClose={() => setDrawerRule(null)}
        title="Evidence Chain"
        subtitle={
          drawerRule
            ? `${drawerRule.rule_id} — ${drawerRule.requirement || ""}`
            : ""
        }
        maxWidth="lg"
      >
        {drawerRule && (
          <div className="space-y-4">
            {/* Verdict */}
            <div className="flex items-center gap-3">
              <ComplianceBadge status={drawerRule.verdict} size="lg" />
              {drawerRule.legal_citation && (
                <p className="text-xs text-slate-500 italic">
                  {drawerRule.legal_citation}
                </p>
              )}
            </div>

            {/* Entity Consistency Block */}
            {drawerRule.entity_consistency && (
              <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Entity Consistency
                  </p>
                  <ComplianceBadge
                    status={
                      drawerRule.entity_consistency.verdict || "NOT_VERIFIED"
                    }
                    size="sm"
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {Object.entries(drawerRule.entity_consistency.names).map(
                    ([src, n]) => {
                      const isOutlier =
                        drawerRule.entity_consistency!.outliers.includes(src);
                      return (
                        <div
                          key={src}
                          className={`rounded-lg border p-2.5 ${
                            isOutlier
                              ? "border-rose-200 bg-rose-50"
                              : "border-slate-200 bg-slate-50"
                          }`}
                        >
                          <p
                            className={`text-[10px] font-black uppercase mb-1 ${
                              isOutlier ? "text-rose-600" : "text-slate-500"
                            }`}
                          >
                            {src}
                            {isOutlier && " ← Outlier"}
                          </p>
                          <p
                            className={`text-xs font-semibold ${
                              isOutlier ? "text-rose-800" : "text-slate-800"
                            }`}
                          >
                            {n.name || "—"}
                          </p>
                          {n.normalized && (
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              {n.normalized}
                            </p>
                          )}
                        </div>
                      );
                    }
                  )}
                </div>
                {drawerRule.entity_consistency.outliers.length > 0 && (
                  <p className="text-xs text-rose-700 font-medium">
                    ⚠ Outlier: {drawerRule.entity_consistency.outliers.join(", ")}
                  </p>
                )}
                {drawerRule.entity_consistency.missing.length > 0 && (
                  <p className="text-xs text-amber-700">
                    Missing documents:{" "}
                    {drawerRule.entity_consistency.missing.join(", ")} →
                    NOT_VERIFIED (not VIOLATION)
                  </p>
                )}
              </div>
            )}

            {/* Evidence References */}
            {drawerRule.evidence_refs.length === 0 && (
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center">
                <p className="text-sm text-slate-500">
                  No evidence references stored for this rule.
                </p>
                {drawerRule.verdict === "NOT_VERIFIED" && (
                  <p className="mt-1 text-xs text-amber-700">
                    Missing evidence produces NOT_VERIFIED, not VIOLATION.
                  </p>
                )}
              </div>
            )}
            {drawerRule.evidence_refs.map((ref, i) => (
              <div
                key={i}
                className="rounded-xl border border-slate-200 bg-slate-50/60 p-4"
              >
                <p className="text-xs font-bold text-slate-800 mb-2">
                  {String(
                    ref.document_filename ||
                      ref.doc_type ||
                      DOC_LABELS[String(ref.doc_type)] ||
                      "Evidence"
                  )}
                </p>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                  {ref.page != null && (
                    <div className="flex gap-2 text-xs">
                      <dt className="shrink-0 font-semibold text-slate-500">
                        Page:
                      </dt>
                      <dd className="text-slate-700">{String(ref.page)}</dd>
                    </div>
                  )}
                  {ref.value != null && (
                    <div className="flex gap-2 text-xs col-span-2">
                      <dt className="shrink-0 font-semibold text-slate-500">
                        Value:
                      </dt>
                      <dd className="text-slate-700 font-mono">
                        {String(ref.value)}
                      </dd>
                    </div>
                  )}
                  {ref.confidence != null && (
                    <div className="flex gap-2 text-xs">
                      <dt className="shrink-0 font-semibold text-slate-500">
                        Confidence:
                      </dt>
                      <dd className="text-slate-700">
                        {Math.round((ref.confidence as number) * 100)}%
                      </dd>
                    </div>
                  )}
                  {ref.source && (
                    <div className="flex gap-2 text-xs">
                      <dt className="shrink-0 font-semibold text-slate-500">
                        Verified via:
                      </dt>
                      <dd className="text-slate-700">{String(ref.source)}</dd>
                    </div>
                  )}
                  {ref.field && (
                    <div className="flex gap-2 text-xs">
                      <dt className="shrink-0 font-semibold text-slate-500">
                        Field:
                      </dt>
                      <dd className="text-slate-700">{String(ref.field)}</dd>
                    </div>
                  )}
                  {Object.entries(ref)
                    .filter(
                      ([k]) =>
                        ![
                          "document_filename",
                          "doc_type",
                          "document_id",
                          "page",
                          "value",
                          "confidence",
                          "source",
                          "origin",
                          "field",
                        ].includes(k)
                    )
                    .map(([k, v]) => (
                      <div key={k} className="flex gap-2 text-xs">
                        <dt className="shrink-0 font-semibold text-slate-500">
                          {k}:
                        </dt>
                        <dd className="min-w-0 break-words text-slate-700">
                          {v === null || v === undefined ? "—" : String(v)}
                        </dd>
                      </div>
                    ))}
                </dl>
              </div>
            ))}

            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
              <strong>Demo Environment:</strong> Government-source verification results shown above are simulated via mock adapters. No live GSTN/PAN/Udyam connection is used.
            </div>
          </div>
        )}
      </Modal>

      {/* Confirm Decision Dialog */}
      <Modal
        isOpen={confirmDecision !== null}
        onClose={() => setConfirmDecision(null)}
        title="Confirm Officer Decision"
        subtitle="This action will be permanently recorded in the audit trail."
        maxWidth="sm"
      >
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-semibold text-slate-700 mb-1">
              Officer Decision:
            </p>
            <DecisionStatusBadge status={confirmDecision || ""} />
            <p className="mt-3 text-sm font-semibold text-slate-700 mb-1">
              Reason / Justification:
            </p>
            <p className="text-sm text-slate-600 bg-white rounded-lg border border-slate-200 p-2.5">
              {reason}
            </p>
          </div>
          <p className="text-xs text-slate-500">
            This decision will be stored with your officer identity, timestamp, and justification in the immutable audit trail.
          </p>
          <div className="flex gap-3">
            <button
              onClick={() => confirmDecision && recordDecision(confirmDecision)}
              disabled={busy}
              className={`flex-1 inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold text-white transition-colors disabled:opacity-50 ${
                confirmDecision === "APPROVE"
                  ? "bg-emerald-600 hover:bg-emerald-700"
                  : confirmDecision === "REJECT"
                  ? "bg-rose-600 hover:bg-rose-700"
                  : "bg-amber-600 hover:bg-amber-700"
              }`}
            >
              {busy ? (
                <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              ) : null}
              Confirm &amp; Record Decision
            </button>
            <button
              onClick={() => setConfirmDecision(null)}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      </Modal>
    </AppShell>
  );
}
