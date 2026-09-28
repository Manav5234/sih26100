"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { ComplianceBadge, DecisionStatusBadge } from "@/components/ui/Badges";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { Modal } from "@/components/ui/Modal";
import { StatCard } from "@/components/ui/StatCard";
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconHistory,
  IconShield,
} from "@/components/ui/Icons";

interface Decision {
  id: string;
  decision: string;
  reason: string | null;
  officer_name: string | null;
  created_at: string;
}

interface EntityConsistency {
  verdict: string | null;
  names: Record<string, { name: string | null; normalized: string | null }>;
  outliers: string[];
  missing: string[];
}

interface RuleResult {
  rule_id: string;
  requirement: string | null;
  verdict: string;
  legal_citation: string | null;
  source: string[];
  evidence_refs: Record<string, unknown>[];
  entity_consistency: EntityConsistency | null;
}

interface ComplianceProfile {
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

interface AuditEvent {
  stage: string;
  detail: Record<string, unknown>;
  timestamp: string;
}

interface DashboardEntry {
  bidder_id: string;
  name: string;
}

async function bearer(): Promise<Record<string, string>> {
  const res = await fetch("/api/auth/token");
  if (!res.ok) return {};
  const data = (await res.json()) as { token?: string | null };
  return data.token ? { Authorization: `Bearer ${data.token}` } : {};
}

export default function BidderCompliancePage() {
  const params = useParams<{ id: string }>();
  const bidderId = params?.id;

  const [profile, setProfile] = useState<ComplianceProfile | null>(null);
  const [profileMissing, setProfileMissing] = useState(false);
  const [name, setName] = useState("");
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [drawerRule, setDrawerRule] = useState<RuleResult | null>(null);

  const load = useCallback(() => {
    if (!bidderId) return;
    const api = getApiUrl();
    Promise.all([
      fetch(`${api}/bidders/${bidderId}/profile`).then((r) =>
        r.status === 404 ? null : r.ok ? r.json() : Promise.reject(new Error(`profile HTTP ${r.status}`)),
      ),
      fetch(`${api}/bidders/${bidderId}/audit`)
        .then((r) => (r.ok ? r.json() : { events: [] }))
        .then((d: { events: AuditEvent[] }) => setEvents(d.events)),
      fetch(`${api}/dashboard`)
        .then((r) => (r.ok ? r.json() : { bidders: [] }))
        .then((d: { bidders: DashboardEntry[] }) =>
          setName(d.bidders.find((b) => b.bidder_id === bidderId)?.name || ""),
        ),
    ])
      .then(([p]) => {
        setProfile(p as ComplianceProfile | null);
        setProfileMissing(p === null);
        setError("");
      })
      .catch(() => setError(`Cannot reach the compliance backend at ${api}`));
  }, [bidderId]);

  useEffect(load, [load]);

  async function runEvaluation() {
    setBusy(true);
    setError("");
    try {
      const headers = await bearer();
      const res = await fetch(`${getApiUrl()}/bidders/${bidderId}/evaluate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Evaluation failed (HTTP ${res.status})`);
      }
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setBusy(false);
    }
  }

  async function recordDecision(decision: string) {
    if (!reason.trim()) {
      setError("A reason is required for every officer decision.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const headers = await bearer();
      if (!headers.Authorization) throw new Error("Sign in again to record a decision.");
      const res = await fetch(`${getApiUrl()}/bidders/${bidderId}/decisions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ decision, reason: reason.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Decision failed (HTTP ${res.status})`);
      }
      setReason("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell officerName={name || "Officer"}>
      <div className="space-y-6">
        <div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <IconArrowLeft className="h-3.5 w-3.5" />
            <span>Dashboard</span>
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              {name || "Bidder compliance"}
            </h1>
            {profile && <DecisionStatusBadge status={profile.decision ? profile.decision.decision : "AWAITING_DECISION"} />}
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {profile?.tender_ref ? `Tender ${profile.tender_ref} — ` : ""}
            stored compliance profile, evidence refs and the officer decision record.
          </p>
        </div>

        <DemoNotice />

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

        {profileMissing && !error && (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-card">
            <h2 className="text-base font-bold text-slate-800">No compliance profile yet</h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
              Run the rule engine for this bidder to store score, risk and rule results.
            </p>
            <button
              onClick={runEvaluation}
              disabled={busy}
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Evaluating…" : "Run evaluation"}
            </button>
          </div>
        )}

        {profile && (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <StatCard
                label="Score"
                value={profile.score ?? "—"}
                supportingText={profile.manual_review ? "Manual review required" : "No manual review flagged"}
                tone="brand"
                icon={<IconShield className="h-5 w-5" />}
              />
              <StatCard
                label="Risk"
                value={profile.risk ?? "—"}
                supportingText={
                  profile.critical_override_fired
                    ? "Critical rule override fired"
                    : "No critical override"
                }
                tone={profile.risk === "HIGH" ? "rose" : profile.risk === "MEDIUM" ? "amber" : "emerald"}
                icon={<IconAlertTriangle className="h-5 w-5" />}
              />
              <StatCard
                label="Rule results"
                value={profile.rule_results.length}
                supportingText={
                  profile.evaluated_at ? `Evaluated ${new Date(profile.evaluated_at).toLocaleString()}` : "Not evaluated"
                }
                tone="purple"
                icon={<IconHistory className="h-5 w-5" />}
              />
            </div>

            {profile.recommendation && (
              <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Engine recommendation
                </p>
                <p className="mt-2 text-sm leading-relaxed text-slate-700">
                  {profile.recommendation}
                </p>
              </div>
            )}

            {/* Rule results + evidence drawer */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
              <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Rule results
                </p>
              </div>
              <div className="divide-y divide-slate-100">
                {profile.rule_results.map((r) => (
                  <div key={r.rule_id} className="px-4 py-3">
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

            {/* Officer decision */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-card space-y-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Officer decision
              </p>
              {profile.decision ? (
                <div className="flex flex-wrap items-center gap-3">
                  <DecisionStatusBadge status={profile.decision.decision} />
                  <span className="text-sm font-semibold text-slate-800">
                    {profile.decision.officer_name || "Officer"}
                  </span>
                  <span className="text-xs text-slate-500">
                    {new Date(profile.decision.created_at).toLocaleString()}
                  </span>
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  No decision recorded yet. The rule engine never decides — only a Procurement Officer does.
                </p>
              )}
              {profile.decision?.reason && (
                <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
                  {profile.decision.reason}
                </p>
              )}
              <div>
                <label
                  htmlFor="decision-reason"
                  className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5"
                >
                  Reason
                </label>
                <textarea
                  id="decision-reason"
                  rows={3}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why this decision? Stored with officer name and timestamp in the audit trail."
                  className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => recordDecision("APPROVE")}
                  disabled={busy}
                  className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  Approve
                </button>
                <button
                  onClick={() => recordDecision("SEND_FOR_CLARIFICATION")}
                  disabled={busy}
                  className="rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  Request clarification
                </button>
                <button
                  onClick={() => recordDecision("REJECT")}
                  disabled={busy}
                  className="rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-rose-700 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            </div>
          </>
        )}

        {/* Audit trail */}
        <div className="rounded-2xl border border-slate-200 bg-white shadow-card">
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
              Audit trail
            </p>
          </div>
          {events.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">No audit events yet.</p>
          ) : (
            <ol className="divide-y divide-slate-100">
              {events.map((ev, i) => (
                <li key={`${ev.stage}-${ev.timestamp}-${i}`} className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xs font-bold text-slate-700">{ev.stage}</span>
                    <span className="text-[11px] text-slate-400">
                      {new Date(ev.timestamp).toLocaleString()}
                    </span>
                  </div>
                  {Object.keys(ev.detail).length > 0 && (
                    <dl className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-0.5">
                      {Object.entries(ev.detail).map(([k, v]) => (
                        <div key={k} className="flex gap-2 text-xs">
                          <dt className="shrink-0 font-semibold text-slate-500">{k}</dt>
                          <dd className="min-w-0 break-words text-slate-700">
                            {v === null || v === undefined ? "—" : String(v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {/* Evidence drawer */}
      <Modal
        isOpen={drawerRule !== null}
        onClose={() => setDrawerRule(null)}
        title="Evidence"
        subtitle={drawerRule ? `${drawerRule.rule_id} — ${drawerRule.requirement || ""}` : ""}
        maxWidth="lg"
      >
        {drawerRule && (
          <div className="space-y-3">
            {drawerRule.evidence_refs.length === 0 && (
              <p className="text-sm text-slate-500">
                No evidence references stored for this rule.
              </p>
            )}
            {drawerRule.evidence_refs.map((ref, i) => (
              <div key={i} className="rounded-xl border border-slate-200 bg-slate-50/60 p-3">
                <p className="text-xs font-bold text-slate-800">
                  {String(ref.document_filename || ref.doc_type || "Evidence")}
                </p>
                <dl className="mt-1.5 space-y-0.5">
                  {Object.entries(ref)
                    .filter(([k]) => !["document_filename", "doc_type", "document_id"].includes(k))
                    .map(([k, v]) => (
                      <div key={k} className="flex gap-2 text-xs">
                        <dt className="shrink-0 font-semibold text-slate-500">{k}</dt>
                        <dd className="min-w-0 break-words text-slate-700">
                          {v === null || v === undefined ? "—" : String(v)}
                        </dd>
                      </div>
                    ))}
                </dl>
              </div>
            ))}

            {drawerRule.entity_consistency && (
              <div className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex items-center gap-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Entity consistency
                  </p>
                  <ComplianceBadge
                    status={drawerRule.entity_consistency.verdict || "NOT_VERIFIED"}
                    size="sm"
                  />
                </div>
                <dl className="mt-2 space-y-0.5">
                  {Object.entries(drawerRule.entity_consistency.names).map(([src, n]) => (
                    <div key={src} className="flex gap-2 text-xs">
                      <dt className="shrink-0 font-semibold text-slate-500">{src}</dt>
                      <dd className="min-w-0 break-words text-slate-700">
                        {n.name || "—"}
                        {n.normalized ? ` (${n.normalized})` : ""}
                      </dd>
                    </div>
                  ))}
                </dl>
                {drawerRule.entity_consistency.outliers.length > 0 && (
                  <p className="mt-2 text-xs text-rose-700">
                    Outliers: {drawerRule.entity_consistency.outliers.join(", ")}
                  </p>
                )}
                {drawerRule.entity_consistency.missing.length > 0 && (
                  <p className="mt-1 text-xs text-amber-700">
                    Missing: {drawerRule.entity_consistency.missing.join(", ")}
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </AppShell>
  );
}
