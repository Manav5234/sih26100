"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, TenderOut, TenderDetailOut } from "@/lib/api";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlertTriangle,
  IconFileText,
  IconUpload,
  IconBriefcase,
  IconCheckCircle,
  IconRefresh,
  IconAI,
} from "@/components/ui/Icons";

export default function TendersPage() {
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [tenderRef, setTenderRef] = useState("");
  const [tenderTitle, setTenderTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // Upload summary result state
  const [uploadResult, setUploadResult] = useState<TenderDetailOut | null>(null);

  const loadTenders = useCallback(async () => {
    try {
      const data = await api.getTenders();
      setTenders(data.tenders || []);
      setError("");
    } catch (err) {
      setTenders([]);
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load tenders list. Please retry."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTenders();
  }, [loadTenders]);


  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setUploadError("Please select a PDF file to upload.");
      return;
    }
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setUploadError("Only PDF documents are supported.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File too large. Maximum supported size is 10 MB.");
      return;
    }

    setUploading(true);
    setUploadError("");
    setUploadResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      if (tenderRef.trim()) form.append("tender_ref", tenderRef.trim());
      if (tenderTitle.trim()) form.append("title", tenderTitle.trim());

      const result = await api.uploadTender(form);
      setUploadResult(result);
      setUploadOpen(false);
      setTenderRef("");
      setTenderTitle("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await loadTenders();
    } catch (err) {
      setUploadError(
        err instanceof Error
          ? err.message
          : "Upload failed. Please verify your officer session and PDF format."
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Active Tenders
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Uploaded tender documents and their extracted, source-cited requirements.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadTenders}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
            >
              <IconRefresh className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </button>
            <button
              onClick={() => {
                setUploadOpen(true);
                setUploadError("");
                setUploadResult(null);
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-brand-700 transition-colors"
            >
              <IconUpload className="h-4 w-4" />
              Upload Tender
            </button>
          </div>
        </div>

        <DemoNotice />

        {/* Upload Success Banner with Extraction Method Detail */}
        {uploadResult && (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50/80 p-5 shadow-card animate-in fade-in duration-200">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-500 text-white shadow-xs">
                  <IconCheckCircle className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-emerald-900">
                      {uploadResult.tender_ref}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase bg-emerald-100 text-emerald-800 border border-emerald-300">
                      Upload Complete
                    </span>
                  </div>
                  <h3 className="mt-1 text-sm font-bold text-emerald-950">
                    {uploadResult.title}
                  </h3>
                  <p className="mt-1 text-xs text-emerald-800">
                    Extracted <strong>{uploadResult.requirement_count} requirements</strong> mapped to compliance verification rules.
                  </p>
                  <div className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium bg-white/80 border-emerald-200 text-slate-700">
                    {uploadResult.extraction_method === "llm" ? (
                      <>
                        <IconAI className="h-3.5 w-3.5 text-brand-600" />
                        <span>Extraction method: <strong>LLM Strict Extraction</strong></span>
                      </>
                    ) : (
                      <>
                        <IconFileText className="h-3.5 w-3.5 text-amber-600" />
                        <span>Extraction method: <strong>Template Fallback</strong> (Ollama offline/fallback used)</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  href={`/tenders/${uploadResult.id}`}
                  className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 transition-colors"
                >
                  View Requirements →
                </Link>
                <button
                  onClick={() => setUploadResult(null)}
                  className="text-xs text-emerald-700 hover:text-emerald-900 font-semibold px-2 py-1"
                >
                  Dismiss
                </button>
              </div>
            </div>
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
              onClick={loadTenders}
              className="font-semibold text-rose-700 hover:text-rose-900 underline ml-2"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && tenders && tenders.length === 0 && !error && (
          <EmptyState
            title="No tenders uploaded"
            description="Upload a tender PDF to extract its requirements and begin compliance evaluation."
          />
        )}

        {tenders && tenders.length > 0 && (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3">Tender Reference</th>
                    <th className="px-4 py-3">Title</th>
                    <th className="px-4 py-3 text-right">Requirements</th>
                    <th className="px-4 py-3">Thresholds</th>
                    <th className="px-4 py-3">Required OEM</th>
                    <th className="px-4 py-3">Uploaded</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {tenders.map((t) => (
                    <tr
                      key={t.id}
                      className="border-b border-slate-100 last:border-0 hover:bg-slate-50/60 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/tenders/${t.id}`}
                          className="inline-flex items-center gap-1.5 font-mono text-xs font-bold text-brand-700 hover:underline"
                        >
                          <IconBriefcase className="h-3.5 w-3.5 text-brand-400" />
                          {t.tender_ref}
                        </Link>
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-800 max-w-xs">
                        {t.title}
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-slate-900">
                        {t.requirement_count}
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600">
                        <div className="space-y-0.5">
                          {t.minimum_turnover != null && (
                            <div>Turnover: ₹{t.minimum_turnover} cr</div>
                          )}
                          {t.bid_value_cr != null && (
                            <div>Bid value: ₹{t.bid_value_cr} cr</div>
                          )}
                          {t.local_content_requirement_applicable && (
                            <div className="text-amber-700 font-medium">
                              Local content: {t.required_local_content_class || "required"}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-700 text-xs">{t.required_oem || "—"}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">
                        {new Date(t.created_at).toLocaleDateString("en-IN", {
                          day: "2-digit",
                          month: "short",
                          year: "numeric",
                        })}
                      </td>
                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <Link
                          href={`/tenders/${t.id}`}
                          className="inline-flex items-center gap-1 rounded-lg border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 transition-colors"
                        >
                          <IconFileText className="h-3.5 w-3.5" />
                          Requirements
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

      {/* Upload Tender Modal */}
      <Modal
        isOpen={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setUploadError("");
        }}
        title="Upload Tender Document"
        subtitle="Upload a GeM tender document (PDF). Clauses will be extracted and linked to compliance rules."
        maxWidth="md"
      >
        <form onSubmit={handleUpload} className="space-y-4">
          {uploadError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              {uploadError}
            </div>
          )}

          <div>
            <label
              htmlFor="tender-file"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
            >
              Tender PDF *
            </label>
            <input
              id="tender-file"
              ref={fileRef}
              type="file"
              accept="application/pdf"
              required
              onChange={(e) => {
                const f = e.target.files?.[0] || null;
                setFile(f);
                if (f && !tenderTitle) {
                  setTenderTitle(f.name.replace(/\.pdf$/i, ""));
                }
              }}
              className="w-full text-xs text-slate-500 file:mr-3 file:py-2 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
            />
            <p className="mt-1 text-[11px] text-slate-400">Maximum file size: 10 MB. PDF text layer / OCR analyzed.</p>
          </div>

          <div>
            <label
              htmlFor="tender-ref"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
            >
              Tender Reference Number (Optional)
            </label>
            <input
              id="tender-ref"
              type="text"
              placeholder="e.g. GEM/2026/T/50005 (auto-generated if blank)"
              value={tenderRef}
              onChange={(e) => setTenderRef(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 font-mono focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div>
            <label
              htmlFor="tender-title"
              className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1"
            >
              Tender Title (Optional)
            </label>
            <input
              id="tender-title"
              type="text"
              placeholder="e.g. Procurement of Network Hardware"
              value={tenderTitle}
              onChange={(e) => setTenderTitle(e.target.value)}
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={uploading || !file}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {uploading ? (
                <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
              ) : (
                <IconUpload className="h-4 w-4" />
              )}
              {uploading ? "Extracting Clauses…" : "Ingest & Extract"}
            </button>
            <button
              type="button"
              onClick={() => {
                setUploadOpen(false);
                setUploadError("");
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
