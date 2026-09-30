"use client";

import React, { useState } from "react";
import Link from "next/link";
import { getApiUrl } from "@/lib/config";
import { Logo } from "@/components/brand/Logo";
import {
  IconArrowLeft,
  IconUpload,
  IconCheckCircle,
  IconAlertTriangle,
  IconInfo,
  IconXCircle,
  IconShield,
} from "@/components/ui/Icons";

// ─── Types ──────────────────────────────────────────────────────────────────

interface DocResult {
  status: "PRESENT" | "UNREADABLE" | "NOT_UPLOADED" | "INVALID_FORMAT" | "TOO_LARGE" | "EXTRACTION_FAILED";
  filename?: string;
  extraction_method?: string;
  fields?: Record<string, { value: string; confidence: number; page: number }>;
  issue?: string;
}

interface EntityCheck {
  verdict: string;
  names: Record<string, { raw: string | null; normalized: string | null }>;
  outliers: string[];
  missing: string[];
  advisory: string;
}

interface SelfCheckResult {
  notice: string;
  documents: Record<string, DocResult>;
  entity_check?: EntityCheck;
  potential_issues: Array<{
    type: string;
    severity: string;
    description: string;
  }>;
  readiness_summary: string;
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function SelfCheckPage() {
  const [panFile, setPanFile] = useState<File | null>(null);
  const [gstFile, setGstFile] = useState<File | null>(null);
  const [udyamFile, setUdyamFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SelfCheckResult | null>(null);
  const [error, setError] = useState("");

  function handleFile(setter: (f: File | null) => void) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0] || null;
      if (file && file.type !== "application/pdf") {
        setError("Only PDF files are accepted.");
        setter(null);
        return;
      }
      setter(file);
      setError("");
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!panFile && !gstFile && !udyamFile) {
      setError("Please upload at least one document to perform the self-check.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);

    const form = new FormData();
    if (panFile) form.append("pan_file", panFile);
    if (gstFile) form.append("gst_file", gstFile);
    if (udyamFile) form.append("udyam_file", udyamFile);

    try {
      const res = await fetch(`${getApiUrl()}/self-check`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error (${res.status})`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Self-check failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function statusIcon(status: string) {
    if (status === "PRESENT") return <IconCheckCircle className="h-4 w-4 text-emerald-600" />;
    if (status === "UNREADABLE" || status === "EXTRACTION_FAILED")
      return <IconXCircle className="h-4 w-4 text-rose-500" />;
    if (status === "NOT_UPLOADED") return <IconInfo className="h-4 w-4 text-slate-400" />;
    return <IconAlertTriangle className="h-4 w-4 text-amber-500" />;
  }

  function statusBadge(status: string) {
    const map: Record<string, string> = {
      PRESENT: "bg-emerald-50 border-emerald-200 text-emerald-700",
      UNREADABLE: "bg-rose-50 border-rose-200 text-rose-700",
      EXTRACTION_FAILED: "bg-rose-50 border-rose-200 text-rose-700",
      NOT_UPLOADED: "bg-slate-100 border-slate-200 text-slate-500",
      INVALID_FORMAT: "bg-amber-50 border-amber-200 text-amber-700",
      TOO_LARGE: "bg-amber-50 border-amber-200 text-amber-700",
    };
    return `inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase ${
      map[status] || "bg-slate-100 border-slate-200 text-slate-500"
    }`;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-6">
          <Logo size="sm" variant="dark" href="/" />
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-slate-800 transition-colors"
          >
            <IconArrowLeft className="h-3.5 w-3.5" />
            Back to Home
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10 space-y-6">
        {/* Non-authoritative notice — prominent */}
        <div className="rounded-2xl border border-amber-300 bg-amber-50 p-5">
          <div className="flex items-start gap-3">
            <IconAlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-extrabold text-amber-900">
                Pre-submission Self-Check — Not an Authoritative Procurement Decision
              </p>
              <p className="mt-1 text-xs leading-relaxed text-amber-800">
                This tool is for your reference only. It checks your documents for readability and
                potential inconsistencies before you submit your bid. The Procurement Officer makes
                all final eligibility determinations. This tool will never say you are
                &ldquo;Qualified&rdquo;, &ldquo;Disqualified&rdquo;, &ldquo;Accepted&rdquo; or
                &ldquo;Rejected&rdquo;.
              </p>
            </div>
          </div>
        </div>

        {/* Upload Form */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-5">
            <h1 className="text-xl font-extrabold tracking-tight text-slate-900">
              Bidder Document Self-Check
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Upload your compliance documents to check for readability and entity consistency.
              Documents are processed and discarded — not stored.
            </p>
          </div>

          {error && (
            <div className="mb-4 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
              <IconAlertTriangle className="h-4 w-4 shrink-0 text-rose-600 mt-0.5" />
              <p>{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {[
              { key: "pan", label: "PAN Certificate", setter: setPanFile, current: panFile },
              { key: "gst", label: "GST Registration Certificate", setter: setGstFile, current: gstFile },
              { key: "udyam", label: "Udyam Registration Certificate", setter: setUdyamFile, current: udyamFile },
            ].map(({ key, label, setter, current }) => (
              <div key={key}>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1.5">
                  {label}
                </label>
                <label className={`flex items-center gap-3 cursor-pointer rounded-xl border px-4 py-3 transition-colors ${
                  current
                    ? "border-emerald-300 bg-emerald-50"
                    : "border-dashed border-slate-300 bg-slate-50 hover:border-brand-400 hover:bg-brand-50/30"
                }`}>
                  <IconUpload className={`h-4 w-4 shrink-0 ${current ? "text-emerald-600" : "text-slate-400"}`} />
                  <span className={`text-sm ${current ? "font-semibold text-emerald-800" : "text-slate-500"}`}>
                    {current ? current.name : `Upload ${label} (PDF)`}
                  </span>
                  {current && (
                    <button
                      type="button"
                      onClick={(e) => { e.preventDefault(); setter(null); }}
                      className="ml-auto text-xs font-semibold text-slate-400 hover:text-rose-600"
                    >
                      Remove
                    </button>
                  )}
                  <input
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={handleFile(setter)}
                  />
                </label>
              </div>
            ))}

            <button
              type="submit"
              disabled={loading || (!panFile && !gstFile && !udyamFile)}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-3 text-sm font-bold text-white hover:bg-brand-700 disabled:opacity-50 disabled:pointer-events-none transition-colors"
            >
              {loading ? (
                <>
                  <span className="h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                  Checking documents…
                </>
              ) : (
                <>
                  <IconShield className="h-4 w-4" />
                  Run Document Self-Check
                </>
              )}
            </button>
          </form>
        </div>

        {/* Results */}
        {result && (
          <div className="space-y-4">
            {/* Non-authoritative reminder */}
            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
              <strong>Reminder:</strong> {result.notice}
            </div>

            {/* Summary */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-2">
                Readiness Summary
              </p>
              <p className="text-sm font-semibold text-slate-800">{result.readiness_summary}</p>
              {result.potential_issues.length === 0 ? (
                <div className="mt-3 flex items-center gap-2 text-xs text-emerald-700">
                  <IconCheckCircle className="h-4 w-4 text-emerald-600" />
                  No potential issues detected in submitted documents.
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  {result.potential_issues.map((issue, i) => (
                    <div
                      key={i}
                      className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
                        issue.severity === "HIGH"
                          ? "bg-rose-50 border border-rose-200 text-rose-800"
                          : "bg-amber-50 border border-amber-200 text-amber-800"
                      }`}
                    >
                      <IconAlertTriangle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                      <span>{issue.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Document status cards */}
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Document Status
                </p>
              </div>
              <div className="divide-y divide-slate-100">
                {(["PAN", "GST", "UDYAM"] as const).map((dt) => {
                  const doc = result.documents[dt] as DocResult | undefined;
                  const status = doc?.status || "NOT_UPLOADED";
                  return (
                    <div key={dt} className="flex items-start gap-4 px-4 py-3">
                      <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${
                        status === "PRESENT"
                          ? "bg-emerald-50 border-emerald-200"
                          : status.includes("FAIL") || status === "UNREADABLE"
                          ? "bg-rose-50 border-rose-200"
                          : "bg-slate-100 border-slate-200"
                      }`}>
                        {statusIcon(status)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-semibold text-slate-800">{dt} Certificate</p>
                          <span className={statusBadge(status)}>{status.replace(/_/g, " ")}</span>
                        </div>
                        {doc?.filename && (
                          <p className="mt-0.5 text-[11px] text-slate-500">{doc.filename}</p>
                        )}
                        {doc?.extraction_method && (
                          <p className="text-[10px] font-mono text-slate-400">{doc.extraction_method} extraction</p>
                        )}
                        {doc?.fields && Object.keys(doc.fields).length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5">
                            {Object.entries(doc.fields).slice(0, 4).map(([field, f]) => (
                              <span key={field} className="text-[11px] text-slate-600">
                                <span className="font-semibold">{field}:</span>{" "}
                                {f.value} ({Math.round(f.confidence * 100)}%, p.{f.page})
                              </span>
                            ))}
                          </div>
                        )}
                        {doc?.issue && (
                          <p className="mt-0.5 text-xs text-rose-700">{doc.issue}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Entity consistency */}
            {result.entity_check && (
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                    Entity Name Consistency
                  </p>
                </div>
                <div className="p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase ${
                      result.entity_check.verdict === "MATCH"
                        ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                        : result.entity_check.verdict === "CONFLICT"
                        ? "bg-rose-50 border-rose-200 text-rose-700"
                        : "bg-amber-50 border-amber-200 text-amber-700"
                    }`}>
                      {result.entity_check.verdict}
                    </span>
                    <span className="text-xs text-slate-600">{result.entity_check.advisory}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {Object.entries(result.entity_check.names).map(([src, n]) => {
                      const isOutlier = result.entity_check!.outliers.includes(src);
                      return (
                        <div
                          key={src}
                          className={`rounded-xl border p-3 ${
                            isOutlier
                              ? "border-rose-200 bg-rose-50"
                              : n.raw === null
                              ? "border-amber-200 bg-amber-50"
                              : "border-slate-200 bg-slate-50"
                          }`}
                        >
                          <p className={`text-[10px] font-black uppercase tracking-wider mb-1 ${
                            isOutlier ? "text-rose-600" : "text-slate-500"
                          }`}>
                            {src}{isOutlier && " ← POTENTIAL OUTLIER"}
                          </p>
                          <p className={`text-sm font-semibold ${
                            isOutlier ? "text-rose-800" : "text-slate-800"
                          }`}>
                            {n.raw || "—"}
                          </p>
                          {n.normalized && n.normalized !== n.raw && (
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Normalized: {n.normalized}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {result.entity_check.verdict === "CONFLICT" && (
                    <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs text-rose-800">
                      <strong>Potential Issue:</strong> Entity name inconsistency detected. This is
                      informational only — it does not constitute automatic disqualification. A Procurement
                      Officer may request clarification or make their own determination during evaluation.
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Back to home */}
            <div className="text-center">
              <Link
                href="/"
                className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700 hover:underline transition-colors"
              >
                <IconArrowLeft className="h-3.5 w-3.5" />
                Back to Home
              </Link>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-400">
        SIH26100 • Bid Compliance Verification Platform •{" "}
        <span className="text-amber-600">
          Pre-submission self-check — not an authoritative procurement decision
        </span>
      </footer>
    </div>
  );
}
