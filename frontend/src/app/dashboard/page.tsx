"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { StatCard } from "@/components/ui/StatCard";
import { DecisionStatusBadge, RiskBadge } from "@/components/ui/Badges";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  IconAlertTriangle,
  IconFileText,
  IconShield,
  IconUsers,
  IconBriefcase,
  IconRefresh,
} from "@/components/ui/Icons";

interface DashboardEntry {
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

interface TenderOut {
  id: string;
  tender_ref: string;
  title: string;
  created_at: string;
  requirement_count: number;
}

export default function DashboardPage() {
  const [entries, setEntries] = useState<DashboardEntry[] | null>(null);
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const api = getApiUrl();
    Promise.all([
      fetch(`${api}/dashboard`)
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data: { bidders: DashboardEntry[]; count: number }) => {
          setEntries(data.bidders);
        }),
      fetch(`${api}/tenders`)
        .then((res) => (res.ok ? res.json() : { tenders: [] }))
        .then((data: { tenders: TenderOut[] }) => setTenders(data.tenders)),
    ])
      .catch(() => {
        setEntries([]);
        setError(`Cannot reach the compliance backend at ${api}`);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const pending = (entries || []).filter((e) => e.pending_review).length;
  const highRisk = (entries || []).filter((e) => e.risk === "HIGH").length;
  const decided = (entries || []).filter((e) =>
    ["APPROVE", "REJECT", "SEND_FOR_CLARIFICATION"].includes(e.status),
  ).length;

  // Group bidders by tender for the tender summary
  const tenderBidderCount: Record<string, number> = {};
  (entries || []).forEach((e) => {
    tenderBidderCount[e.tender_ref] = (tenderBidderCount[e.tender_ref] || 0) + 1;
  });

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Officer Dashboard
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Stored compliance submissions across all tenders — nothing is re-evaluated on page load.
            </p>
          </div>
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
          >
            <IconRefresh className="h-3.5 w-3.5" />
            Refresh
          </button>
        </div>

        <DemoNotice />

        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
            <div>
              <p className="font-bold">Backend unreachable</p>
              <p className="mt-0.5 text-rose-700">{error}</p>
            </div>
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <StatCard
            label="Total Tenders"
            value={loading ? "—" : (tenders?.length ?? 0)}
            supportingText="Uploaded & extracted"
            tone="brand"
            icon={<IconFileText className="h-5 w-5" />}
          />
          <StatCard
            label="Total Bidders"
            value={loading ? "—" : (entries?.length ?? 0)}
            supportingText="Across all tenders"
            tone="purple"
            icon={<IconUsers className="h-5 w-5" />}
          />
          <StatCard
            label="Pending Review"
            value={loading ? "—" : pending}
            supportingText="Undecided or flagged"
            tone="amber"
            icon={<IconAlertTriangle className="h-5 w-5" />}
          />
          <StatCard
            label="High Risk"
            value={loading ? "—" : highRisk}
            supportingText="Critical override fired"
            tone="rose"
            icon={<IconShield className="h-5 w-5" />}
          />
        </div>

        {/* Active Tenders Summary */}
        {tenders && tenders.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Active Tenders
              </p>
              <Link href="/tenders" className="text-xs font-semibold text-brand-600 hover:text-brand-700 hover:underline">
                View all →
              </Link>
            </div>
            <div className="divide-y divide-slate-100">
              {tenders.slice(0, 5).map((t) => (
                <div key={t.id} className="flex items-center gap-4 px-4 py-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 border border-brand-100">
                    <IconBriefcase className="h-4 w-4 text-brand-600" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-mono text-xs font-bold text-brand-700">{t.tender_ref}</p>
                    <p className="mt-0.5 text-xs text-slate-500 truncate">{t.title}</p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 text-xs text-slate-500">
                    <span className="font-semibold text-slate-700">{t.requirement_count} requirements</span>
                    <span className="text-slate-400">{tenderBidderCount[t.tender_ref] ?? 0} bidders</span>
                  </div>
                  <Link
                    href={`/tenders/${t.id}`}
                    className="shrink-0 rounded-lg border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
                  >
                    View
                  </Link>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty States */}
        {!loading && entries && entries.length === 0 && !error && (
          <EmptyState
            title="No bidders yet"
            description="Upload a tender and run the seeding script, or create bidders manually after uploading a tender."
            actionLabel="Go to Tenders"
            actionHref="/tenders"
          />
        )}

        {/* Bidders Compliance Table */}
        {entries && entries.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Compliance Overview — All Bidders
              </p>
              <span className="text-xs text-slate-400">{entries.length} bidders</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/60 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3">Bidder</th>
                    <th className="px-4 py-3">Tender</th>
                    <th className="px-4 py-3 text-right">Score</th>
                    <th className="px-4 py-3">Risk</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Evaluated</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr
                      key={e.bidder_id}
                      className={`border-b border-slate-100 last:border-0 hover:bg-slate-50/60 transition-colors ${
                        e.risk === "HIGH" ? "bg-rose-50/30" : ""
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {e.risk === "HIGH" && (
                            <IconAlertTriangle className="h-3.5 w-3.5 text-rose-500 shrink-0" />
                          )}
                          <span className="font-semibold text-slate-800">{e.name}</span>
                        </div>
                        {e.pending_review && (
                          <span className="mt-0.5 block text-[11px] font-semibold text-amber-600">
                            ⚠ Needs attention
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/tenders/${e.tender_id}`}
                          className="font-mono text-xs font-semibold text-brand-700 hover:underline"
                        >
                          {e.tender_ref}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {e.score !== null ? (
                          <div className="inline-flex flex-col items-end">
                            <span className="text-base font-black text-slate-900">{e.score}</span>
                            <span className="text-[10px] text-slate-400">/ 100</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 text-xs">Not evaluated</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <RiskBadge risk={e.risk} />
                      </td>
                      <td className="px-4 py-3">
                        <DecisionStatusBadge status={e.status} />
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-400">
                        {e.evaluated_at
                          ? new Date(e.evaluated_at).toLocaleDateString("en-IN", {
                              day: "2-digit",
                              month: "short",
                              year: "numeric",
                            })
                          : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/bidders/${e.bidder_id}`}
                          className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 transition-colors"
                        >
                          Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Summary Footer */}
            <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-2.5 flex flex-wrap gap-4 text-xs text-slate-500">
              <span>
                <strong className="text-emerald-700">{decided}</strong> decisions recorded
              </span>
              <span>
                <strong className="text-amber-700">{pending}</strong> pending officer action
              </span>
              <span>
                <strong className="text-rose-700">{highRisk}</strong> HIGH risk
              </span>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
