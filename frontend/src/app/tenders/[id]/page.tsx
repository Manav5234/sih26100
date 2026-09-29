"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, RequirementListResponse } from "@/lib/api";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconAlertTriangle, IconArrowLeft, IconRefresh } from "@/components/ui/Icons";

export default function TenderRequirementsPage() {
  const params = useParams<{ id: string }>();
  const tenderId = params?.id;
  const [data, setData] = useState<RequirementListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRequirements = useCallback(async () => {
    if (!tenderId) return;
    try {
      const res = await api.getTenderRequirements(tenderId);
      setData(res);
      setError("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load tender requirements. Please retry."
      );
    } finally {
      setLoading(false);
    }
  }, [tenderId]);

  useEffect(() => {
    if (tenderId) {
      loadRequirements();
    }
  }, [tenderId, loadRequirements]);


  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <Link
              href="/tenders"
              className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
            >
              <IconArrowLeft className="h-3.5 w-3.5" />
              <span>All Tenders</span>
            </Link>
            <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-slate-900">
              {data ? data.tender_ref : "Tender Requirements"}
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              {data
                ? `${data.requirements.length} extracted requirements, each joined to its source clause and legal rule.`
                : "Loading requirements…"}
            </p>
          </div>
          <button
            onClick={loadRequirements}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
          >
            <IconRefresh className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        <DemoNotice />

        {error && (
          <div className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
            <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Backend Service Notice</p>
              <p className="mt-0.5 text-rose-700">{error}</p>
            </div>
            <button
              onClick={loadRequirements}
              className="font-semibold text-rose-700 hover:text-rose-900 underline ml-2"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && data && data.requirements.length === 0 && (
          <EmptyState
            title="No requirements extracted"
            description="This tender has no stored requirements."
            actionLabel="Back to Tenders"
            actionHref="/tenders"
          />
        )}

        {data && data.requirements.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Requirement</th>
                    <th className="px-4 py-3">Source Clause</th>
                    <th className="px-4 py-3">Required Evidence</th>
                    <th className="px-4 py-3">Rule Reference</th>
                  </tr>
                </thead>
                <tbody>
                  {data.requirements.map((r) => (
                    <tr
                      key={r.id}
                      className="border-b border-slate-100 last:border-0 align-top hover:bg-slate-50/40 transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-600 whitespace-nowrap">
                        {r.requirement_id}
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        <p className="font-semibold text-slate-800">{r.title}</p>
                        <p className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-400">
                          {r.category}
                        </p>
                      </td>
                      <td className="px-4 py-3 max-w-md text-xs text-slate-600 leading-relaxed">
                        {r.source_clause || "—"}
                      </td>
                      <td className="px-4 py-3 max-w-[14rem]">
                        <div className="flex flex-wrap gap-1">
                          {r.required_evidence.length === 0 && (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                          {r.required_evidence.map((ev) => (
                            <span
                              key={ev}
                              className="inline-flex rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] font-medium text-slate-600"
                            >
                              {ev}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-mono text-xs font-bold text-brand-700">
                          {r.rule_id}
                        </p>
                        {r.rule?.source && (
                          <p className="mt-0.5 max-w-[16rem] text-[11px] leading-relaxed text-slate-500">
                            {r.rule.source}
                          </p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
