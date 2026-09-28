"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { DecisionStatusBadge, RiskBadge } from "@/components/ui/Badges";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlertTriangle,
  IconUsers,
  IconPlus,
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
}

export default function BiddersPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<DashboardEntry[] | null>(null);
  const [tenders, setTenders] = useState<TenderOut[]>([]);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [filterRisk, setFilterRisk] = useState("ALL");
  const [filterStatus, setFilterStatus] = useState("ALL");

  // Create bidder form state
  const [bidderName, setBidderName] = useState("");
  const [bidderLegal, setBidderLegal] = useState("");
  const [selectedTender, setSelectedTender] = useState("");

  const load = useCallback(() => {
    const api = getApiUrl();
    Promise.all([
      fetch(`${api}/dashboard`)
        .then((r) => (r.ok ? r.json() : { bidders: [] }))
        .then((d: { bidders: DashboardEntry[] }) => setEntries(d.bidders)),
      fetch(`${api}/tenders`)
        .then((r) => (r.ok ? r.json() : { tenders: [] }))
        .then((d: { tenders: TenderOut[] }) => setTenders(d.tenders)),
    ]).catch(() => {
      setEntries([]);
      setError(`Cannot reach the compliance backend at ${api}`);
    });
  }, []);

  useEffect(load, [load]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!bidderName.trim() || !selectedTender) {
      setCreateError("Bidder name and tender are required.");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const res = await fetch(`${getApiUrl()}/bidders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: bidderName.trim(),
          legal_name: bidderLegal.trim() || bidderName.trim(),
          tender_id: selectedTender,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Create failed (HTTP ${res.status})`);
      }
      const data = await res.json() as { id: string };
      setCreateOpen(false);
      setBidderName("");
      setBidderLegal("");
      setSelectedTender("");
      load();
      // Navigate to the new bidder page
      router.push(`/bidders/${data.id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create bidder.");
    } finally {
      setCreating(false);
    }
  }

  const filtered = (entries || []).filter((e) => {
    if (filterRisk !== "ALL" && e.risk !== filterRisk) return false;
    if (filterStatus === "PENDING" && !e.pending_review) return false;
    if (filterStatus === "DECIDED" && !["APPROVE", "REJECT", "SEND_FOR_CLARIFICATION"].includes(e.status)) return false;
    return true;
  });

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Bidders</h1>
            <p className="mt-1 text-sm text-slate-500">
              All bidders across tenders with their compliance profiles.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition-colors"
            >
              <IconRefresh className="h-3.5 w-3.5" />
              Refresh
            </button>
            <button
              onClick={() => { setCreateOpen(true); setCreateError(""); }}
              className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-brand-700 transition-colors"
            >
              <IconPlus className="h-4 w-4" />
              New Bidder
            </button>
          </div>
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

        {/* Filters */}
        {entries && entries.length > 0 && (
          <div className="flex flex-wrap gap-3 items-center">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Filter:</span>
            <div className="flex gap-2">
              {["ALL", "LOW", "MEDIUM", "HIGH"].map((r) => (
                <button
                  key={r}
                  onClick={() => setFilterRisk(r)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold border transition-colors ${
                    filterRisk === r
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"
                  }`}
                >
                  {r === "ALL" ? "All Risk" : `${r} Risk`}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              {[
                { val: "ALL", label: "All Status" },
                { val: "PENDING", label: "Pending Review" },
                { val: "DECIDED", label: "Decision Made" },
              ].map((s) => (
                <button
                  key={s.val}
                  onClick={() => setFilterStatus(s.val)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold border transition-colors ${
                    filterStatus === s.val
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {entries && entries.length === 0 && !error && (
          <EmptyState
            title="No bidders yet"
            description="Create a bidder against a tender, then upload documents and run evaluation."
            actionLabel="Upload a Tender first"
            actionHref="/tenders"
          />
        )}

        {entries && entries.length > 0 && filtered.length === 0 && (
          <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-card">
            <IconUsers className="mx-auto h-8 w-8 text-slate-300 mb-3" />
            <p className="text-sm font-semibold text-slate-700">No bidders match the current filters.</p>
            <button
              onClick={() => { setFilterRisk("ALL"); setFilterStatus("ALL"); }}
              className="mt-2 text-xs text-brand-600 hover:underline"
            >
              Clear filters
            </button>
          </div>
        )}

        {filtered.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                {filtered.length} Bidder{filtered.length !== 1 ? "s" : ""}
                {(filterRisk !== "ALL" || filterStatus !== "ALL") && " (filtered)"}
              </p>
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
                  {filtered.map((e) => (
                    <tr
                      key={e.bidder_id}
                      className={`border-b border-slate-100 last:border-0 hover:bg-slate-50/60 transition-colors ${
                        e.risk === "HIGH" ? "bg-rose-50/20" : ""
                      }`}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <Link
                            href={`/bidders/${e.bidder_id}`}
                            className="font-semibold text-slate-800 hover:text-brand-700 hover:underline"
                          >
                            {e.name}
                          </Link>
                          {e.pending_review && (
                            <span className="ml-2 inline-flex items-center rounded-md bg-amber-100 border border-amber-200 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">
                              NEEDS REVIEW
                            </span>
                          )}
                        </div>
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
                          <span className="text-base font-black text-slate-900">{e.score}</span>
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
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
          </div>
        )}
      </div>

      {/* Create Bidder Modal */}
      <Modal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create New Bidder"
        subtitle="Register a bidder against a tender to begin document upload and compliance evaluation."
        maxWidth="md"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {createError && (
            <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
              <p>{createError}</p>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Bidder / Company Name <span className="text-rose-500">*</span>
            </label>
            <input
              type="text"
              value={bidderName}
              onChange={(e) => setBidderName(e.target.value)}
              placeholder="e.g. ABC Technologies Pvt Ltd"
              required
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Legal Name
            </label>
            <input
              type="text"
              value={bidderLegal}
              onChange={(e) => setBidderLegal(e.target.value)}
              placeholder="Legal entity name (if different)"
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Tender <span className="text-rose-500">*</span>
            </label>
            {tenders.length === 0 ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                No tenders found. <Link href="/tenders" className="font-semibold underline">Upload a tender first.</Link>
              </div>
            ) : (
              <select
                value={selectedTender}
                onChange={(e) => setSelectedTender(e.target.value)}
                required
                className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20 bg-white"
              >
                <option value="">Select a tender…</option>
                {tenders.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.tender_ref} — {t.title}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className="pt-1 flex gap-3">
            <button
              type="submit"
              disabled={creating || !bidderName.trim() || !selectedTender}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50 disabled:pointer-events-none transition-colors"
            >
              {creating ? (
                <>
                  <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Creating…
                </>
              ) : (
                "Create Bidder"
              )}
            </button>
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </Modal>
    </AppShell>
  );
}
