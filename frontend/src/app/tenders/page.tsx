"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { IconAlertTriangle, IconFileText } from "@/components/ui/Icons";

interface TenderOut {
  id: string;
  tender_ref: string;
  title: string;
  created_at: string;
  requirement_count: number;
  required_oem: string | null;
  required_local_content_class: string | null;
}

export default function TendersPage() {
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${getApiUrl()}/tenders`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: { tenders: TenderOut[] }) => {
        setTenders(data.tenders);
        setError("");
      })
      .catch(() => {
        setTenders([]);
        setError(`Cannot reach the compliance backend at ${getApiUrl()}`);
      });
  }, []);

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Tenders</h1>
          <p className="mt-1 text-sm text-slate-500">
            Uploaded tender documents and their extracted, source-cited requirements.
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

        {tenders && tenders.length === 0 && !error && (
          <EmptyState
            title="No tenders uploaded"
            description="Upload a tender PDF to extract its requirements."
          />
        )}

        {tenders && tenders.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-3">Tender ref</th>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3">Requirements</th>
                  <th className="px-4 py-3">Required OEM</th>
                  <th className="px-4 py-3">Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {tenders.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/tenders/${t.id}`}
                        className="inline-flex items-center gap-1.5 font-mono text-xs font-semibold text-brand-700 hover:underline"
                      >
                        <IconFileText className="h-3.5 w-3.5" />
                        {t.tender_ref}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-800">{t.title}</td>
                    <td className="px-4 py-3 text-slate-700">{t.requirement_count}</td>
                    <td className="px-4 py-3 text-slate-700">{t.required_oem || "—"}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {new Date(t.created_at).toLocaleString()}
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
