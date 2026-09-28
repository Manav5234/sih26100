"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import {
  IconAlertTriangle,
  IconFileText,
  IconUpload,
  IconBriefcase,
} from "@/components/ui/Icons";

interface TenderOut {
  id: string;
  tender_ref: string;
  title: string;
  created_at: string;
  requirement_count: number;
  required_oem: string | null;
  required_local_content_class: string | null;
  minimum_turnover: number | null;
  bid_value_cr: number | null;
  local_content_requirement_applicable: boolean;
}

async function bearer(): Promise<Record<string, string>> {
  const res = await fetch("/api/auth/token");
  if (!res.ok) return {};
  const data = (await res.json()) as { token?: string | null };
  return data.token ? { Authorization: `Bearer ${data.token}` } : {};
}

export default function TendersPage() {
  const [tenders, setTenders] = useState<TenderOut[] | null>(null);
  const [error, setError] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [tenderRef, setTenderRef] = useState("");
  const [tenderTitle, setTenderTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function loadTenders() {
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
  }

  useEffect(loadTenders, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setUploadError("Please select a PDF file.");
      return;
    }
    if (file.type !== "application/pdf") {
      setUploadError("Only PDF files are supported.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError("File must be under 10 MB.");
      return;
    }

    setUploading(true);
    setUploadError("");
    try {
      const headers = await bearer();
      if (!headers.Authorization) {
        setUploadError("You must be signed in to upload a tender. Please sign in and try again.");
        setUploading(false);
        return;
      }

      const form = new FormData();
      form.append("file", file);
      if (tenderRef.trim()) form.append("tender_ref", tenderRef.trim());
      if (tenderTitle.trim()) form.append("title", tenderTitle.trim());

      const res = await fetch(`${getApiUrl()}/tenders/upload`, {
        method: "POST",
        headers,
        body: form,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => null);
        if (res.status === 409) {
          throw new Error(`Tender reference "${tenderRef}" already exists. Use a unique reference.`);
        }
        throw new Error(body?.detail || `Upload failed (HTTP ${res.status})`);
      }

      // Success
      setUploadOpen(false);
      setTenderRef("");
      setTenderTitle("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      loadTenders();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed. Please try again.");
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
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">Tenders</h1>
            <p className="mt-1 text-sm text-slate-500">
              Uploaded tender documents and their extracted, source-cited requirements.
            </p>
          </div>
          <button
            onClick={() => {
              setUploadOpen(true);
              setUploadError("");
            }}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-brand-700 transition-colors"
          >
            <IconUpload className="h-4 w-4" />
            Upload Tender
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

        {tenders && tenders.length === 0 && !error && (
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
        title="Upload Tender"
        subtitle="PDF is processed using text layer extraction with OCR fallback and LLM field extraction."
        maxWidth="md"
      >
        <form onSubmit={handleUpload} className="space-y-4">
          {uploadError && (
            <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
              <p>{uploadError}</p>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Tender Reference
            </label>
            <input
              type="text"
              value={tenderRef}
              onChange={(e) => setTenderRef(e.target.value)}
              placeholder="e.g. GEM/2026/T/50002"
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
            <p className="mt-1 text-[11px] text-slate-400">Leave blank to auto-generate.</p>
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Tender Title
            </label>
            <input
              type="text"
              value={tenderTitle}
              onChange={(e) => setTenderTitle(e.target.value)}
              placeholder="e.g. Supply of Signalling Equipment"
              className="w-full rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-600 focus:outline-none focus:ring-3 focus:ring-brand-500/20"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
              Tender PDF <span className="text-rose-500">*</span>
            </label>
            <div
              className="relative flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center hover:border-brand-400 hover:bg-brand-50/30 transition-colors cursor-pointer"
              onClick={() => fileRef.current?.click()}
            >
              <IconUpload className="h-8 w-8 text-slate-400 mb-2" />
              <p className="text-sm font-semibold text-slate-700">
                {file ? file.name : "Click to select PDF"}
              </p>
              <p className="mt-1 text-xs text-slate-400">
                {file
                  ? `${(file.size / 1024).toFixed(0)} KB`
                  : "PDF only · max 10 MB"}
              </p>
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>
          </div>

          <div className="pt-1 flex gap-3">
            <button
              type="submit"
              disabled={uploading || !file}
              className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50 disabled:pointer-events-none transition-colors"
            >
              {uploading ? (
                <>
                  <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  <span>Extracting...</span>
                </>
              ) : (
                <>
                  <IconUpload className="h-4 w-4" />
                  <span>Upload & Extract</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={() => setUploadOpen(false)}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
          </div>

          <p className="text-[11px] text-slate-400 text-center">
            If LLM extraction fails, the system uses a controlled template fallback.
            The extraction method is always shown in the results.
          </p>
        </form>
      </Modal>
    </AppShell>
  );
}
