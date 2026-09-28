"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  IconHistory,
  IconSearch,
  IconFilter,
  IconAlertTriangle,
  IconCheckCircle,
  IconConflict,
  IconShield,
  IconFileText,
  IconUsers,
  IconRefresh,
} from "@/components/ui/Icons";

interface AuditEvent {
  stage: string;
  detail: Record<string, unknown>;
  timestamp: string;
  bidder_id?: string | null;
  tender_id?: string | null;
  actor?: string | null;
}

interface DashboardEntry {
  bidder_id: string;
  name: string;
  tender_id: string;
  tender_ref: string | null;
  score: number | null;
  risk: string | null;
  status: string;
}

export default function AuditTrailPage() {
  const [bidders, setBidders] = useState<DashboardEntry[]>([]);
  const [selectedBidderId, setSelectedBidderId] = useState<string>("all");
  const [allEvents, setAllEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [stageFilter, setStageFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);

  const loadAuditData = useCallback(async () => {
    setLoading(true);
    setError("");
    const api = getApiUrl();
    try {
      // 1. Fetch dashboard entries to get all active bidders
      const dashRes = await fetch(`${api}/dashboard`);
      if (!dashRes.ok) throw new Error(`Dashboard HTTP ${dashRes.status}`);
      const dashData = await dashRes.json();
      const bidderList: DashboardEntry[] = dashData.bidders || [];
      setBidders(bidderList);

      // 2. Fetch audit events for all bidders (combining their timelines)
      const eventPromises = bidderList.map((b) =>
        fetch(`${api}/bidders/${b.bidder_id}/audit`)
          .then((res) => (res.ok ? res.json() : { events: [] }))
          .then((d) => (d.events || []).map((e: AuditEvent) => ({ ...e, bidder_id: b.bidder_id })))
          .catch(() => [] as AuditEvent[])
      );

      const nestedEvents = await Promise.all(eventPromises);
      const flattened = nestedEvents.flat();

      // Deduplicate events by timestamp + stage + bidder_id
      const seen = new Set<string>();
      const uniqueEvents: AuditEvent[] = [];
      for (const ev of flattened) {
        const key = `${ev.timestamp}_${ev.stage}_${ev.bidder_id || ""}_${JSON.stringify(ev.detail)}`;
        if (!seen.has(key)) {
          seen.add(key);
          uniqueEvents.push(ev);
        }
      }

      // Sort newest first
      uniqueEvents.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setAllEvents(uniqueEvents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load audit events");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAuditData();
  }, [loadAuditData]);

  // Filtering
  const filteredEvents = allEvents.filter((ev) => {
    if (selectedBidderId !== "all" && ev.bidder_id !== selectedBidderId) {
      return false;
    }
    if (stageFilter !== "ALL" && ev.stage !== stageFilter) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const stageMatch = ev.stage.toLowerCase().includes(q);
      const detailMatch = JSON.stringify(ev.detail).toLowerCase().includes(q);
      const bidderMatch = ev.bidder_id
        ? (bidders.find((b) => b.bidder_id === ev.bidder_id)?.name || "").toLowerCase().includes(q)
        : false;
      return stageMatch || detailMatch || bidderMatch;
    }
    return true;
  });

  const getStageColor = (stage: string) => {
    if (stage.includes("CONFLICT") || stage.includes("VIOLATION")) {
      return "bg-rose-50 text-rose-700 border-rose-200";
    }
    if (stage.includes("DECISION") || stage.includes("OFFICER")) {
      return "bg-purple-50 text-purple-700 border-purple-200";
    }
    if (stage.includes("RULES") || stage.includes("EVALUATED")) {
      return "bg-brand-50 text-brand-700 border-brand-200";
    }
    if (stage.includes("SOURCE") || stage.includes("IDENTITY")) {
      return "bg-amber-50 text-amber-700 border-amber-200";
    }
    if (stage.includes("UPLOADED") || stage.includes("EXTRACTED") || stage.includes("CREATED")) {
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    }
    return "bg-slate-50 text-slate-700 border-slate-200";
  };

  const getStageDot = (stage: string) => {
    if (stage.includes("CONFLICT")) return "bg-rose-500 ring-rose-200";
    if (stage.includes("DECISION")) return "bg-purple-500 ring-purple-200";
    if (stage.includes("RULES")) return "bg-brand-500 ring-brand-200";
    if (stage.includes("IDENTITY") || stage.includes("SOURCE")) return "bg-amber-500 ring-amber-200";
    return "bg-emerald-500 ring-emerald-200";
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Audit Trail & Verification Logs
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Immutable ledger of all tender processing, identity verifications, deterministic rule evaluations, and officer decisions.
            </p>
          </div>
          <button
            onClick={loadAuditData}
            disabled={loading}
            className="inline-flex items-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition-all disabled:opacity-60"
          >
            <IconRefresh className={`h-4 w-4 text-slate-500 ${loading ? "animate-spin" : ""}`} />
            Refresh Trail
          </button>
        </div>

        <DemoNotice />

        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
            <div>
              <p className="font-bold">Audit Service Notice</p>
              <p className="mt-0.5 text-rose-700">{error}</p>
            </div>
          </div>
        )}

        {/* Filters and search bar */}
        <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
          <div className="relative flex-1">
            <IconSearch className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search stage, bidder name, or details…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-2 pl-10 pr-4 text-xs text-slate-800 placeholder-slate-400 focus:border-brand-500 focus:bg-white focus:outline-hidden"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Bidder dropdown */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-500">Bidder:</span>
              <select
                value={selectedBidderId}
                onChange={(e) => setSelectedBidderId(e.target.value)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 focus:border-brand-500 focus:outline-hidden"
              >
                <option value="all">All Bidders ({bidders.length})</option>
                {bidders.map((b) => (
                  <option key={b.bidder_id} value={b.bidder_id}>
                    {b.name} ({b.tender_ref || "Tender"})
                  </option>
                ))}
              </select>
            </div>

            {/* Stage filter */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-500">Stage:</span>
              <select
                value={stageFilter}
                onChange={(e) => setStageFilter(e.target.value)}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 focus:border-brand-500 focus:outline-hidden"
              >
                <option value="ALL">All Stages</option>
                <option value="TENDER_UPLOADED">TENDER_UPLOADED</option>
                <option value="REQUIREMENTS_EXTRACTED">REQUIREMENTS_EXTRACTED</option>
                <option value="BIDDER_CREATED">BIDDER_CREATED</option>
                <option value="DOCUMENT_UPLOADED">DOCUMENT_UPLOADED</option>
                <option value="OCR_COMPLETED">OCR_COMPLETED</option>
                <option value="FIELDS_EXTRACTED">FIELDS_EXTRACTED</option>
                <option value="SOURCE_CHECKED">SOURCE_CHECKED</option>
                <option value="ENTITY_CONSISTENCY_CHECK">ENTITY_CONSISTENCY_CHECK</option>
                <option value="RULES_EVALUATED">RULES_EVALUATED</option>
                <option value="CONFLICT_DETECTED">CONFLICT_DETECTED</option>
                <option value="OFFICER_DECISION_RECORDED">OFFICER_DECISION_RECORDED</option>
              </select>
            </div>
          </div>
        </div>

        {/* Timeline representation */}
        {loading ? (
          <div className="flex h-48 items-center justify-center rounded-2xl border border-slate-200 bg-white shadow-card">
            <div className="flex items-center gap-3 text-slate-500 text-xs">
              <span className="h-4 w-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin" />
              Loading audit timeline…
            </div>
          </div>
        ) : filteredEvents.length === 0 ? (
          <EmptyState
            title="No audit events found"
            description={
              allEvents.length === 0
                ? "No audit events recorded yet. Upload a tender or evaluate a bidder to begin generating audit trail logs."
                : "No events match the current filter selection."
            }
            actionLabel="Go to Dashboard"
            actionHref="/dashboard"
          />
        ) : (
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card">
            <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-200">
              {filteredEvents.map((ev, idx) => {
                const bidder = bidders.find((b) => b.bidder_id === ev.bidder_id);
                const isExpanded = expandedIndex === idx;
                const formattedTime = new Date(ev.timestamp).toLocaleString("en-IN", {
                  dateStyle: "medium",
                  timeStyle: "medium",
                });

                return (
                  <div key={idx} className="relative group">
                    {/* Pulsing or solid dot */}
                    <div
                      className={`absolute -left-6 top-1 h-3.5 w-3.5 rounded-full ring-4 ring-offset-2 ${getStageDot(
                        ev.stage
                      )}`}
                    />

                    <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 transition-all hover:border-slate-300 hover:bg-slate-50">
                      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={`inline-flex items-center rounded-lg border px-2.5 py-0.5 text-xs font-mono font-bold ${getStageColor(
                              ev.stage
                            )}`}
                          >
                            {ev.stage}
                          </span>
                          {bidder && (
                            <Link
                              href={`/bidders/${bidder.bidder_id}`}
                              className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-semibold text-slate-700 hover:text-brand-600 hover:border-brand-200 transition-colors"
                            >
                              <IconUsers className="h-3 w-3 text-slate-400" />
                              <span>{bidder.name}</span>
                            </Link>
                          )}
                          {ev.actor && (
                            <span className="text-[11px] font-medium text-slate-500">
                              by <strong className="text-slate-700">{ev.actor}</strong>
                            </span>
                          )}
                        </div>
                        <time className="text-xs font-mono text-slate-400 whitespace-nowrap">
                          {formattedTime}
                        </time>
                      </div>

                      {/* Detail preview */}
                      <div className="mt-3 text-xs text-slate-600">
                        {ev.stage === "RULES_EVALUATED" && (
                          <div className="space-y-1">
                            <p className="font-semibold text-slate-800">
                              {ev.detail.results_count !== undefined ? String(ev.detail.results_count) : "13"} compliance rules evaluated against tender requirements.
                            </p>
                            {Boolean(ev.detail.verdicts) && typeof ev.detail.verdicts === "object" && (
                              <div className="flex flex-wrap gap-2 text-[11px] pt-1">
                                {Object.entries(ev.detail.verdicts as Record<string, number>).map(([v, count]) => (
                                  <span
                                    key={v}
                                    className="rounded bg-white border border-slate-200 px-1.5 py-0.5 font-medium text-slate-700"
                                  >
                                    <strong>{count}</strong> {v.toLowerCase().replace("_", " ")}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        {ev.stage === "OFFICER_DECISION_RECORDED" && (
                          <div className="space-y-1">
                            <p className="font-semibold text-slate-800">
                              Officer decision: <span className="font-mono text-brand-700 font-bold">{String(ev.detail.decision || "RECORDED")}</span>
                            </p>
                            {Boolean(ev.detail.reason) && (
                              <p className="text-slate-600 italic">&ldquo;{String(ev.detail.reason)}&rdquo;</p>
                            )}
                          </div>
                        )}

                        {ev.stage === "ENTITY_CONSISTENCY_CHECK" && (
                          <div className="space-y-1">
                            <p className="font-semibold text-slate-800">
                              Cross-document identity verification completed. Verdict:{" "}
                              <strong className={ev.detail.verdict === "MATCH" ? "text-emerald-700" : "text-rose-700"}>
                                {String(ev.detail.verdict || "UNKNOWN")}
                              </strong>
                            </p>
                          </div>
                        )}

                        {ev.stage === "DOCUMENT_UPLOADED" && (
                          <p className="text-slate-700">
                            Uploaded document: <strong className="font-mono">{String(ev.detail.filename || ev.detail.doc_type || "PDF")}</strong>
                            {ev.detail.page_count ? ` (${ev.detail.page_count} pages)` : ""}
                          </p>
                        )}

                        {ev.stage === "SOURCE_CHECKED" && (
                          <p className="text-slate-700">
                            Mock adapter verified <strong className="font-mono">{String(ev.detail.source || "registry")}</strong> status:{" "}
                            <span className="font-semibold text-emerald-700">{String(ev.detail.status || "VERIFIED")}</span>
                          </p>
                        )}
                      </div>

                      {/* Expandable JSON detail */}
                      <div className="mt-3 pt-2 border-t border-slate-200/60 flex items-center justify-between text-[11px]">
                        <button
                          onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                          className="font-semibold text-brand-600 hover:text-brand-800 transition-colors"
                        >
                          {isExpanded ? "Hide raw payload ▲" : "View audit payload ▼"}
                        </button>
                        <span className="text-slate-400 font-mono">
                          ID: {ev.stage}_{idx + 1}
                        </span>
                      </div>

                      {isExpanded && (
                        <pre className="mt-2.5 overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-300">
                          {JSON.stringify(ev.detail, null, 2)}
                        </pre>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
