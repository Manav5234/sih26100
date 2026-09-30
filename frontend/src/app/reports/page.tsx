"use client";

import React, { useEffect, useState } from "react";
import { api, DashboardEntry, ComplianceReport } from "@/lib/api";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { ComplianceBadge, DecisionStatusBadge, RiskBadge } from "@/components/ui/Badges";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  IconFileText,
  IconDownload,
  IconShield,
  IconAlertTriangle,
  IconCheckCircle,
  IconRefresh,
  IconUsers,
} from "@/components/ui/Icons";

export default function ReportsPage() {
  const [bidders, setBidders] = useState<DashboardEntry[]>([]);
  const [selectedBidderId, setSelectedBidderId] = useState<string>("");
  const [report, setReport] = useState<ComplianceReport | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function init() {
      try {
        const data = await api.getDashboard();
        const list = (data.bidders || []).filter((b) => b.score !== null || b.risk !== null);
        setBidders(list);
        if (list.length > 0) {
          setSelectedBidderId(list[0].bidder_id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load bidders");
      } finally {
        setLoadingList(false);
      }
    }
    init();
  }, []);

  useEffect(() => {
    if (!selectedBidderId) {
      setReport(null);
      return;
    }
    async function loadReport() {
      setLoadingReport(true);
      setError("");
      try {
        const rep = await api.getBidderReport(selectedBidderId);
        setReport(rep);
      } catch (err) {
        setReport(null);
        setError(err instanceof Error ? err.message : "Failed to load compliance report");
      } finally {
        setLoadingReport(false);
      }
    }
    loadReport();
  }, [selectedBidderId]);

  function handlePrint() {
    window.print();
  }

  function handleDownloadJson() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `compliance_report_${report.tender.tender_ref?.replace(/\//g, "_")}_${report.bidder.name.replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header - Hidden during print */}
        <div className="print:hidden flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Compliance Reports &amp; Exports
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Authoritative, printable compliance dossiers for Procurement Officers. All findings are traceable to stored evaluation records.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handlePrint}
              disabled={!report}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 transition-colors shadow-xs"
            >
              <IconDownload className="h-3.5 w-3.5" />
              Print / Save PDF
            </button>
            <button
              onClick={handleDownloadJson}
              disabled={!report}
              className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-3.5 py-2 text-xs font-bold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors shadow-xs"
            >
              Export JSON
            </button>
          </div>
        </div>

        <DemoNotice className="print:hidden" />

        {/* Bidder Selector - Hidden during print */}
        <div className="print:hidden flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
          <label htmlFor="bidder-select" className="text-xs font-bold uppercase tracking-wider text-slate-600">
            Select Bidder Dossier:
          </label>
          <select
            id="bidder-select"
            value={selectedBidderId}
            onChange={(e) => setSelectedBidderId(e.target.value)}
            disabled={loadingList || bidders.length === 0}
            className="rounded-xl border border-slate-300 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-800 focus:border-brand-600 focus:outline-none"
          >
            {bidders.map((b) => (
              <option key={b.bidder_id} value={b.bidder_id}>
                {b.name} ({b.tender_ref}) — Risk: {b.risk || "PENDING"} — Score: {b.score ?? "—"}
              </option>
            ))}
          </select>
          {loadingReport && (
            <span className="flex items-center gap-1 text-xs text-slate-400">
              <IconRefresh className="h-3.5 w-3.5 animate-spin" />
              Loading report…
            </span>
          )}
        </div>

        {error && (
          <div className="print:hidden flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Error loading dossier</p>
              <p className="mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {bidders.length === 0 && !loadingList && !error && (
          <EmptyState
            title="No evaluated dossiers found"
            description="Reports are generated from evaluated bidder submissions. Go to Bidders to run rule evaluations."
            actionLabel="View Bidders"
            actionHref="/bidders"
          />
        )}

        {/* ─── OFFICIAL PRINTABLE REPORT CONTAINER ──────────────────────────────── */}
        {report && (
          <div className="rounded-2xl border border-slate-300 bg-white p-8 sm:p-12 shadow-card print:border-none print:shadow-none print:p-0 space-y-8 text-slate-900">
            {/* Government Dossier Header */}
            <div className="border-b-2 border-slate-900 pb-6 flex flex-wrap justify-between items-start gap-4">
              <div>
                <div className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white mb-2">
                  <span>GeM Procurement Authority</span>
                </div>
                <h2 className="text-2xl font-black tracking-tight text-slate-900">
                  BID COMPLIANCE EVALUATION REPORT
                </h2>
                <p className="text-xs font-mono text-slate-500 mt-1">
                  Document Reference: GeM-COMP-{report.tender.tender_ref?.replace(/\//g, "-")}-{report.bidder.id.substring(0, 8)}
                </p>
              </div>
              <div className="text-right text-xs text-slate-500 space-y-1">
                <p>
                  <strong className="text-slate-700">Generated:</strong>{" "}
                  {new Date(report.generated_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST
                </p>
                <p>
                  <strong className="text-slate-700">Classification:</strong> Official — Procurement Sensitive
                </p>
              </div>
            </div>

            {/* Advisory Principle Notice */}
            <div className="rounded-xl border border-amber-300 bg-amber-50/70 p-4 text-xs text-amber-900 space-y-1">
              <p className="font-extrabold uppercase tracking-wide flex items-center gap-1.5">
                <IconShield className="h-4 w-4 text-amber-700 shrink-0" />
                Statutory Architecture Principle: AI Verifies. Evidence Explains. Officer Decides.
              </p>
              <p className="leading-relaxed text-amber-800">
                {report.advisory_notice} The system does not automatically qualify or disqualify any bidder. Numerical scores and rule flags serve as deterministic decision support.
              </p>
            </div>

            {/* Target Information Table */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 rounded-xl border border-slate-200 bg-slate-50/50 p-5">
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Tender Information
                </p>
                <p className="font-mono text-xs font-bold text-brand-700">
                  {report.tender.tender_ref || "—"}
                </p>
                <p className="text-sm font-semibold text-slate-800">
                  {report.tender.title || "—"}
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Bidder Particulars
                </p>
                <p className="text-sm font-bold text-slate-900">{report.bidder.name}</p>
                <p className="text-xs text-slate-600">
                  Legal Name: <span className="font-medium">{report.bidder.legal_name || "—"}</span>
                </p>
              </div>
            </div>

            {/* Evaluation Summary & Scores */}
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="rounded-xl border border-slate-200 p-4 bg-white">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Compliance Score
                </p>
                <p className="mt-1 text-3xl font-black text-slate-900">
                  {report.evaluation.score !== null ? `${report.evaluation.score}/100` : "—"}
                </p>
                <p className="text-[10px] text-slate-400 mt-1">Weighted rule satisfaction</p>
              </div>

              <div className="rounded-xl border border-slate-200 p-4 bg-white">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Assessed Risk
                </p>
                <div className="mt-1">
                  <RiskBadge risk={report.evaluation.risk} />
                </div>
                {report.evaluation.critical_override_fired && (
                  <p className="text-[10px] text-rose-600 font-bold mt-1">Critical Override Fired</p>
                )}
              </div>

              <div className="rounded-xl border border-slate-200 p-4 bg-white">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Evaluated Rules
                </p>
                <p className="mt-1 text-3xl font-black text-slate-900">
                  {report.evaluation.rule_count}
                </p>
                <p className="text-[10px] text-slate-400 mt-1">Against tender requirements</p>
              </div>

              <div className="rounded-xl border border-slate-200 p-4 bg-white">
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                  Decision Status
                </p>
                <div className="mt-1">
                  <DecisionStatusBadge
                    status={report.officer_decision.latest ? report.officer_decision.latest.decision : "AWAITING_DECISION"}
                  />
                </div>
                <p className="text-[10px] text-slate-400 mt-1">
                  {report.officer_decision.latest ? "Officer decided" : "Action pending"}
                </p>
              </div>
            </div>

            {/* SEPARATED RECOMMENDATION VS OFFICER DECISION (Phase 19 Requirement) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Left: System Recommendation */}
              <div className="rounded-xl border-2 border-amber-300 bg-amber-50/40 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-black uppercase tracking-wider text-amber-900 bg-amber-200/70 border border-amber-300 px-2 py-0.5 rounded-md">
                    {report.system_recommendation.label}
                  </span>
                </div>
                <p className="text-sm font-semibold text-amber-950 leading-relaxed">
                  {report.system_recommendation.text || "No recommendation generated."}
                </p>
                <p className="text-[11px] text-amber-800 leading-normal">
                  Note: Deterministic rule synthesis only. Does not replace officer judgment.
                </p>
              </div>

              {/* Right: Officer Final Decision */}
              <div className="rounded-xl border-2 border-slate-800 bg-slate-50 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-black uppercase tracking-wider text-white bg-slate-900 px-2 py-0.5 rounded-md">
                    {report.officer_decision.label}
                  </span>
                  {report.officer_decision.latest && (
                    <span className="text-xs font-mono text-slate-500">
                      {new Date(report.officer_decision.latest.recorded_at).toLocaleDateString("en-IN")}
                    </span>
                  )}
                </div>
                {report.officer_decision.latest ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <DecisionStatusBadge status={report.officer_decision.latest.decision} />
                      <span className="text-xs font-bold text-slate-800">
                        Recorded by {report.officer_decision.latest.officer_name || "Procurement Officer"}
                      </span>
                    </div>
                    <div className="rounded-lg bg-white border border-slate-200 p-3 text-xs text-slate-800">
                      <strong className="text-slate-900 block mb-1">Officer Justification:</strong>
                      {report.officer_decision.latest.reason}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-slate-300 bg-white p-4 text-center">
                    <p className="text-xs text-slate-500 font-medium">
                      No decision recorded by Procurement Officer yet.
                    </p>
                    <p className="text-[11px] text-slate-400 mt-1">
                      Final qualification/disqualification decision must be recorded by the officer.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Rule-by-rule Verification Findings */}
            <div className="space-y-3">
              <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-900 border-b border-slate-200 pb-2">
                Detailed Requirement Verifications ({report.rule_results.length})
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs border border-slate-200">
                  <thead>
                    <tr className="bg-slate-100 text-left font-bold uppercase tracking-wider text-slate-700 border-b border-slate-200">
                      <th className="p-3 w-28">Rule ID</th>
                      <th className="p-3">Requirement &amp; Legal Citation</th>
                      <th className="p-3 w-32">Verdict</th>
                      <th className="p-3">Evidence Traced</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {report.rule_results.map((r) => (
                      <tr key={r.rule_id} className="hover:bg-slate-50/50">
                        <td className="p-3 font-mono font-bold text-brand-700 align-top">
                          {r.rule_id}
                        </td>
                        <td className="p-3 align-top max-w-sm">
                          <p className="font-semibold text-slate-800">{r.requirement || r.rule_id}</p>
                          {r.legal_citation && (
                            <p className="text-[11px] text-slate-500 mt-0.5">{r.legal_citation}</p>
                          )}
                        </td>
                        <td className="p-3 align-top">
                          <ComplianceBadge status={r.verdict} size="sm" />
                        </td>
                        <td className="p-3 align-top text-[11px] text-slate-600">
                          {r.evidence_refs && r.evidence_refs.length > 0 ? (
                            <ul className="list-disc pl-4 space-y-0.5">
                              {r.evidence_refs.map((ev, i) => (
                                <li key={i}>
                                  <span className="font-semibold">{ev.path}</span>
                                  {ev.value ? `: ${ev.value}` : ""}
                                  {ev.page ? ` (p.${ev.page})` : ""}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span className="text-slate-400">No external document evidence required</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Official Footer / Sign-off block for printing */}
            <div className="pt-10 border-t-2 border-slate-900 grid grid-cols-2 gap-8 text-xs text-slate-600">
              <div>
                <p className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                  Procurement Officer Verification
                </p>
                <div className="mt-8 border-b border-slate-400 w-48" />
                <p className="mt-1 font-semibold text-slate-700">
                  {report.officer_decision.latest?.officer_name || "Authorized Officer"}
                </p>
                <p className="text-[11px] text-slate-400">GeM Procurement Directorate</p>
              </div>
              <div className="text-right">
                <p className="font-bold text-slate-800 uppercase tracking-wider text-[11px]">
                  System Integrity Seal
                </p>
                <p className="mt-2 font-mono text-[10px] text-slate-400">
                  SHA-256 Checksum: Verified
                </p>
                <p className="mt-1 text-[10px] text-slate-400">
                  {report.demo_notice}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
