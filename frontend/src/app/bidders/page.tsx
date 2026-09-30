"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, DashboardEntry, TenderOut } from "@/lib/api";
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

export default function BiddersPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<DashboardEntry[] | null>(null);
  const [tenders, setTenders] = useState<TenderOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [filterRisk, setFilterRisk] = useState("ALL");
  const [filterStatus, setFilterStatus] = useState("ALL");
  const [filterTender, setFilterTender] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  // Create bidder form state
  const [bidderName, setBidderName] = useState("");
  const [bidderLegal, setBidderLegal] = useState("");
  const [selectedTender, setSelectedTender] = useState("");

  const fetchBiddersData = async () => {
    try {
      const [dashData, tendersData] = await Promise.all([
        api.getDashboard(),
        api.getTenders().catch(() => ({ tenders: [], count: 0 })),
      ]);
      setEntries(dashData.bidders || []);
      setTenders(tendersData.tenders || []);
      setError("");
    } catch (err) {
      setEntries([]);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load bidders directory. Please retry."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBiddersData();
  }, []);

  const handleRefresh = () => {
    setLoading(true);
    fetchBiddersData();
  };

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!bidderName.trim() || !selectedTender) {
      setCreateError("Bidder name and tender are required.");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const newBidder = await api.createBidder({
        name: bidderName.trim(),
        legal_name: bidderLegal.trim() || bidderName.trim(),
        tender_id: selectedTender,
      });
      setCreateOpen(false);
      setBidderName("");
      setBidderLegal("");
      setSelectedTender("");
      await fetchBiddersData();
      router.push(`/bidders/${newBidder.id}`);
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Failed to create bidder."
      );
    } finally {
      setCreating(false);
    }
  }

  const filtered = (entries || []).filter((e) => {
    if (filterRisk !== "ALL" && e.risk !== filterRisk) return false;
    if (filterTender !== "ALL" && e.tender_id !== filterTender && e.tender_ref !== filterTender) return false;
    if (filterStatus === "PENDING" && !e.pending_review) return false;
    if (
      filterStatus === "DECIDED" &&
      !["APPROVE", "REJECT", "SEND_FOR_CLARIFICATION"].includes(e.status)
    )
      return false;
    if (["APPROVE", "REJECT", "SEND_FOR_CLARIFICATION", "AWAITING_DECISION"].includes(filterStatus) && e.status !== filterStatus) {
      return false;
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = e.name.toLowerCase().includes(q);
      const matchRef = e.tender_ref.toLowerCase().includes(q);
      if (!matchName && !matchRef) return false;
    }
    return true;
  });

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Bidders Directory
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              All submitted bidders across active tenders with their compliance profiles and evaluation statuses.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
            >
              <IconRefresh className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              onClick={() => {
                setCreateOpen(true);
                setCreateError("");
              }}
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
            <div className="flex-1">
              <p className="font-bold">Backend Service Notice</p>
              <p className="mt-0.5 text-rose-700">{error}</p>
            </div>
            <button
              onClick={handleRefresh}
              className="font-semibold text-rose-700 hover:text-rose-900 underline ml-2"
            >
              Retry
            </button>
          </div>
        )}

        {/* Filters & Search */}
        {entries && entries.length > 0 && (
          <div className="space-y-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-card">
            <div className="flex flex-wrap gap-3 items-center">
              <div className="flex-1 min-w-[200px]">
                <input
                  type="text"
                  placeholder="Search bidders by name or tender reference..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 px-3.5 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none"
                />
              </div>

              {tenders.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-bold uppercase text-slate-500">Tender:</span>
                  <select
                    value={filterTender}
                    onChange={(e) => setFilterTender(e.target.value)}
                    className="rounded-xl border border-slate-300 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-700 focus:border-brand-600 focus:outline-none"
                  >
                    <option value="ALL">All Tenders</option>
                    {tenders.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.tender_ref}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-2 items-center pt-2 border-t border-slate-100">
              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mr-1">
                Risk:
              </span>
              {["ALL", "LOW", "MEDIUM", "HIGH"].map((r) => (
                <button
                  key={r}
                  onClick={() => setFilterRisk(r)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold border transition-colors ${
                    filterRisk === r
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"
                  }`}
                >
                  {r === "ALL" ? "All Risk" : `${r}`}
                </button>
              ))}

              <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider ml-3 mr-1">
                Decision Status:
              </span>
              {[
                { val: "ALL", label: "All" },
                { val: "PENDING", label: "Needs Action" },
                { val: "APPROVE", label: "Approved" },
                { val: "REJECT", label: "Rejected" },
                { val: "SEND_FOR_CLARIFICATION", label: "Clarification" },
              ].map((s) => (
                <button
                  key={s.val}
                  onClick={() => setFilterStatus(s.val)}
                  className={`rounded-lg px-2.5 py-1 text-xs font-semibold border transition-colors ${
                    filterStatus === s.val
                      ? "bg-brand-600 text-white border-brand-600"
                      : "border-slate-200 text-slate-600 bg-white hover:bg-slate-50"
                  }`}
                >
                  {s.label}
                </button>
              ))}

              {(searchQuery || filterRisk !== "ALL" || filterStatus !== "ALL" || filterTender !== "ALL") && (
                <button
                  onClick={() => {
                    setSearchQuery("");
                    setFilterRisk("ALL");
                    setFilterStatus("ALL");
                    setFilterTender("ALL");
                  }}
                  className="ml-auto text-xs font-semibold text-rose-600 hover:underline"
                >
                  Reset filters
                </button>
              )}
            </div>
          </div>
        )}

        {!loading && entries && entries.length === 0 && !error && (
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
            <p className="text-sm font-semibold text-slate-700">
              No bidders match the current filters.
            </p>
            <button
              onClick={() => {
                setFilterRisk("ALL");
                setFilterStatus("ALL");
              }}
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
                            className="font-semibold text-slate-900 hover:text-brand-600 transition-colors flex items-center gap-1.5"
                          >
                            {e.risk === "HIGH" && (
                              <IconAlertTriangle className="h-3.5 w-3.5 text-rose-500 shrink-0" />
                            )}
                            {e.name}
                          </Link>
                          {e.pending_review && (
                            <span className="mt-0.5 block text-[11px] font-semibold text-amber-600">
                              ⚠ Needs attention
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
                          <div className="inline-flex flex-col items-end">
                            <span className="text-base font-black text-slate-900">
                              {e.score}
                            </span>
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
                          Open Profile
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
        onClose={() => {
          setCreateOpen(false);
          setCreateError("");
        }}
        title="Create New Bidder"
        subtitle="Register a bidder against an active tender to begin document collection."
        maxWidth="md"
      >
        <form onSubmit={handleCreate} className="space-y-4">
          {createError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              {createError}
            </div>
          )}

          <div>
            <label
              htmlFor="bidder-tender"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
            >
              Associated Tender *
            </label>
            <select
              id="bidder-tender"
              required
              value={selectedTender}
              onChange={(e) => setSelectedTender(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            >
              <option value="">Select a tender…</option>
              {tenders.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.tender_ref} — {t.title}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="bidder-name"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
            >
              Bidder / Trade Name *
            </label>
            <input
              id="bidder-name"
              type="text"
              required
              placeholder="e.g. ABC Technologies Pvt Ltd"
              value={bidderName}
              onChange={(e) => setBidderName(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div>
            <label
              htmlFor="bidder-legal"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
            >
              Legal Entity Name (Optional)
            </label>
            <input
              id="bidder-legal"
              type="text"
              placeholder="e.g. ABC Technologies Private Limited"
              value={bidderLegal}
              onChange={(e) => setBidderLegal(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={creating || !bidderName.trim() || !selectedTender}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {creating ? (
                <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              ) : null}
              {creating ? "Creating…" : "Create & Open Workspace"}
            </button>
            <button
              type="button"
              onClick={() => {
                setCreateOpen(false);
                setCreateError("");
              }}
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
