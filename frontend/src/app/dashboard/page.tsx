"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { StatCard } from "@/components/ui/StatCard";
import { DecisionStatusBadge, RiskBadge } from "@/components/ui/Badges";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconAlertTriangle, IconFileText, IconShield } from "@/components/ui/Icons";

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

export default function DashboardPage() {
  const [entries, setEntries] = useState<DashboardEntry[] | null>(null);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    fetch(`${getApiUrl()}/dashboard`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: { bidders: DashboardEntry[]; count: number }) => {
        setEntries(data.bidders);
        setCount(data.count);
        setError("");
      })
      .catch(() => {
        setEntries([]);
        setError(`Cannot reach the compliance backend at ${getApiUrl()}`);
      });
  }, []);

  useEffect(load, [load]);

  const pending = (entries || []).filter((e) => e.pending_review).length;
  const decided = (entries || []).filter((e) =>
    ["APPROVE", "REJECT", "SEND_FOR_CLARIFICATION"].includes(e.status),
  ).length;

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
            Officer Dashboard
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Stored compliance submissions across all tenders — nothing is re-evaluated on page load.
          </p>
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

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            label="Bidders"
            value={entries ? count : "—"}
            supportingText="Across all tenders"
            tone="brand"
            icon={<IconFileText className="h-5 w-5" />}
          />
          <StatCard
            label="Pending review"
            value={entries ? pending : "—"}
            supportingText="Undecided or flagged by rules"
            tone="amber"
            icon={<IconAlertTriangle className="h-5 w-5" />}
          />
          <StatCard
            label="Decisions recorded"
            value={entries ? decided : "—"}
            supportingText="Officer Approve / Reject / Clarify"
            tone="emerald"
            icon={<IconShield className="h-5 w-5" />}
          />
        </div>

        {entries && entries.length === 0 && !error && (
          <EmptyState
            title="No bidders yet"
            description="Upload a tender and bidder documents, then run an evaluation to populate the dashboard."
            actionLabel="Go to Tenders"
            actionHref="/tenders"
          />
        )}

        {entries && entries.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Bidder</th>
                  <th className="px-4 py-3">Tender</th>
                  <th className="px-4 py-3 text-right">Score</th>
                  <th className="px-4 py-3">Risk</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr
                    key={e.bidder_id}
                    className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60"
                  >
                    <td className="px-4 py-3 font-semibold text-slate-800">{e.name}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/tenders/${e.tender_id}`}
                        className="font-mono text-xs font-semibold text-brand-700 hover:underline"
                      >
                        {e.tender_ref}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-slate-900">
                      {e.score ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <RiskBadge risk={e.risk} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <DecisionStatusBadge status={e.status} />
                        {e.pending_review && (
                          <span className="text-[11px] font-semibold text-amber-700">
                            needs attention
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/bidders/${e.bidder_id}`}
                        className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 transition-colors"
                      >
                        Open compliance
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
