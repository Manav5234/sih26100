"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, RequirementListResponse, RequirementOut } from "@/lib/api";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconRefresh,
  IconCheckCircle,
  IconFileText,
} from "@/components/ui/Icons";

export default function TenderRequirementsPage() {
  const params = useParams<{ id: string }>();
  const tenderId = params?.id;
  const [data, setData] = useState<RequirementListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Requirement Modal / Edit State
  const [selectedReq, setSelectedReq] = useState<RequirementOut | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editClause, setEditClause] = useState("");
  const [editEvidence, setEditEvidence] = useState("");
  const [editCategory, setEditCategory] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

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

  function openReqDetail(req: RequirementOut) {
    setSelectedReq(req);
    setIsEditing(false);
    setEditTitle(req.title);
    setEditClause(req.source_clause || "");
    setEditEvidence((req.required_evidence || []).join(", "));
    setEditCategory(req.category || "");
    setSaveError("");
  }

  async function handleSaveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!tenderId || !selectedReq) return;
    setSaving(true);
    setSaveError("");
    try {
      const evidenceList = editEvidence
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const updated = await api.updateRequirement(tenderId, selectedReq.id, {
        title: editTitle.trim(),
        source_clause: editClause.trim(),
        required_evidence: evidenceList,
        category: editCategory.trim() || undefined,
      });

      setSelectedReq(updated);
      setIsEditing(false);
      setSuccessMsg(`Requirement ${updated.requirement_id} metadata updated successfully.`);
      await loadRequirements();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to update requirement.");
    } finally {
      setSaving(false);
    }
  }

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

        {successMsg && (
          <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800">
            <IconCheckCircle className="h-4 w-4 shrink-0 text-emerald-600 mt-0.5" />
            <div className="flex-1">
              <p className="font-bold">Requirement Updated</p>
              <p className="mt-0.5 text-emerald-700">{successMsg}</p>
            </div>
            <button
              onClick={() => setSuccessMsg("")}
              className="font-semibold text-emerald-700 hover:text-emerald-900"
            >
              Dismiss
            </button>
          </div>
        )}

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
            <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3 flex items-center justify-between">
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Extracted Requirements Checklist (Click to inspect or review)
              </p>
              <span className="text-xs text-slate-400 font-medium">
                {data.requirements.length} rules mapped
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Requirement</th>
                    <th className="px-4 py-3">Source Clause</th>
                    <th className="px-4 py-3">Required Evidence</th>
                    <th className="px-4 py-3">Rule Reference</th>
                    <th className="px-4 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.requirements.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => openReqDetail(r)}
                      className="border-b border-slate-100 last:border-0 align-top hover:bg-slate-50/70 transition-colors cursor-pointer group"
                    >
                      <td className="px-4 py-3 font-mono text-xs font-semibold text-slate-600 whitespace-nowrap">
                        {r.requirement_id}
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        <p className="font-semibold text-slate-800 group-hover:text-brand-700 transition-colors">
                          {r.title}
                        </p>
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
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <span className="inline-flex items-center rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 group-hover:border-brand-300 group-hover:bg-brand-50 group-hover:text-brand-700 transition-all">
                          Inspect →
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ─── REQUIREMENT DETAIL & CONTROLLED EDIT MODAL ──────────────────────── */}
        {selectedReq && (
          <Modal
            isOpen={Boolean(selectedReq)}
            onClose={() => setSelectedReq(null)}
            title={`Requirement ${selectedReq.requirement_id}`}
            size="lg"
          >
            <div className="space-y-5">
              {saveError && (
                <div className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
                  <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
                  <p>{saveError}</p>
                </div>
              )}

              {/* Immutable Rule Engine Metadata */}
              <div className="rounded-xl border border-brand-100 bg-brand-50/60 p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-black uppercase tracking-wider text-brand-700 bg-brand-200/60 px-2 py-0.5 rounded">
                    Fixed Rule Mapping
                  </span>
                  <span className="font-mono text-xs font-bold text-brand-900">
                    {selectedReq.rule_id}
                  </span>
                </div>
                {selectedReq.rule?.source && (
                  <p className="text-xs text-slate-700 leading-relaxed">
                    <strong className="text-slate-900">Statutory / Legal Source:</strong>{" "}
                    {selectedReq.rule.source}
                  </p>
                )}
                {selectedReq.rule?.description && (
                  <p className="text-xs text-slate-600">
                    <strong className="text-slate-900">Rule Logic:</strong>{" "}
                    {selectedReq.rule.description}
                  </p>
                )}
                <p className="text-[11px] text-brand-800/80">
                  Rule evaluation algorithms and pass/fail/conflict conditions are config-driven and cannot be arbitrarily changed from the frontend.
                </p>
              </div>

              {!isEditing ? (
                /* Read-only View */
                <div className="space-y-4 text-xs">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                      Requirement Title
                    </span>
                    <p className="text-sm font-bold text-slate-900">{selectedReq.title}</p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                        Category
                      </span>
                      <p className="font-semibold text-slate-800 uppercase">{selectedReq.category || "GENERAL"}</p>
                    </div>
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-0.5">
                        Source Tender Clause
                      </span>
                      <p className="font-semibold text-slate-800">{selectedReq.source_clause || "—"}</p>
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block mb-1">
                      Required Evidences
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedReq.required_evidence.map((ev) => (
                        <span
                          key={ev}
                          className="inline-flex rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs font-semibold text-slate-700"
                        >
                          {ev}
                        </span>
                      ))}
                      {selectedReq.required_evidence.length === 0 && (
                        <span className="text-slate-400 italic">None specified</span>
                      )}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-slate-100 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setIsEditing(true)}
                      className="rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                      Edit Metadata
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedReq(null)}
                      className="rounded-xl bg-brand-600 px-4 py-2 text-xs font-bold text-white hover:bg-brand-700 transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : (
                /* Controlled Metadata Edit Form */
                <form onSubmit={handleSaveEdit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                      Title
                    </label>
                    <input
                      type="text"
                      required
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-brand-600 focus:outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                        Category
                      </label>
                      <input
                        type="text"
                        value={editCategory}
                        onChange={(e) => setEditCategory(e.target.value)}
                        className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-brand-600 focus:outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                        Source Clause Reference
                      </label>
                      <input
                        type="text"
                        value={editClause}
                        onChange={(e) => setEditClause(e.target.value)}
                        className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-brand-600 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                      Required Evidence (comma-separated)
                    </label>
                    <input
                      type="text"
                      value={editEvidence}
                      onChange={(e) => setEditEvidence(e.target.value)}
                      placeholder="e.g. PAN Certificate, GST Registration"
                      className="w-full rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:border-brand-600 focus:outline-none"
                    />
                  </div>

                  <div className="pt-4 border-t border-slate-100 flex justify-end gap-2">
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => setIsEditing(false)}
                      className="rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={saving}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-brand-600 px-4 py-2 text-xs font-bold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
                    >
                      {saving ? "Saving…" : "Save Metadata"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </Modal>
        )}
      </div>
    </AppShell>
  );
}
