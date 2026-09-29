"use client";

import React, { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getApiUrl } from "@/lib/config";
import { AppShell } from "@/components/layout/AppShell";
import { DemoNotice } from "@/components/ui/DemoNotice";
import {
  IconShield,
  IconCheckCircle,
  IconRefresh,
  IconBriefcase,
  IconFileText,
} from "@/components/ui/Icons";

interface HealthState {
  status: "checking" | "healthy" | "unreachable";
  service?: string;
  latencyMs?: number;
  url: string;
}

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthState>({
    status: "checking",
    url: getApiUrl(),
  });

  const checkHealth = useCallback(async () => {
    const res = await api.checkHealth();
    setHealth({
      status: res.status,
      service: res.service,
      latencyMs: res.latencyMs,
      url: getApiUrl(),
    });
  }, []);

  const handlePing = () => {
    setHealth({ status: "checking", url: getApiUrl() });
    checkHealth();
  };

  useEffect(() => {
    checkHealth();
  }, [checkHealth]);


  return (
    <AppShell>
      <div className="space-y-6 max-w-5xl mx-auto">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
            System Settings &amp; Platform Health
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Operational status, deterministic rule configuration, and system architecture specifications.
          </p>
        </div>

        <DemoNotice />

        {/* Backend health banner */}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 border border-brand-200 text-brand-700">
                <IconShield className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Backend Health &amp; Service Connectivity
                </h2>
                <p className="text-xs text-slate-500 font-mono mt-0.5">{health.url}</p>
              </div>
            </div>
            <button
              onClick={handlePing}
              disabled={health.status === "checking"}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-xs hover:bg-slate-50 transition-all disabled:opacity-60"
            >
              <IconRefresh
                className={`h-3.5 w-3.5 ${health.status === "checking" ? "animate-spin" : ""}`}
              />
              Ping API
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
            <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                API Status
              </span>
              <div className="mt-1.5 flex items-center gap-2">
                {health.status === "healthy" ? (
                  <>
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-xs shadow-emerald-400" />
                    <span className="text-sm font-bold text-emerald-700">Operational (HTTP 200)</span>
                  </>
                ) : health.status === "checking" ? (
                  <>
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-400 animate-ping" />
                    <span className="text-sm font-bold text-amber-700">Checking…</span>
                  </>
                ) : (
                  <>
                    <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
                    <span className="text-sm font-bold text-rose-700">Unreachable</span>
                  </>
                )}
              </div>
            </div>

            <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Response Latency
              </span>
              <p className="mt-1.5 text-sm font-mono font-bold text-slate-800">
                {health.latencyMs !== undefined ? `${health.latencyMs} ms` : "—"}
              </p>
            </div>

            <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Microservice
              </span>
              <p className="mt-1.5 text-sm font-mono font-bold text-slate-800">
                {health.service || "sih26100-backend"}
              </p>
            </div>
          </div>
        </div>

        {/* Configuration and Specifications */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Rules engine info */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700">
                <IconCheckCircle className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Deterministic Rule Engine</h3>
            </div>
            <dl className="divide-y divide-slate-100 text-xs">
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Config Schema Version</dt>
                <dd className="font-mono font-bold text-slate-800">v1.1.0</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Configured Rules</dt>
                <dd className="font-mono font-bold text-slate-800">13 Rules</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Critical Override Rule IDs</dt>
                <dd className="font-mono text-slate-800">DEBARMENT-001, ENTITY-CONSISTENCY-001</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Logic Formulation</dt>
                <dd className="font-semibold text-slate-800">Kleene 3-Valued Logic</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Decision Authority</dt>
                <dd className="font-bold text-brand-700">Human Procurement Officer Only</dd>
              </div>
            </dl>
          </div>

          {/* Government Adapter Mocks */}
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-card space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-50 border border-indigo-200 text-indigo-700">
                <IconBriefcase className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-slate-900">Government Source Adapters</h3>
            </div>
            <dl className="divide-y divide-slate-100 text-xs">
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">PAN Verification</dt>
                <dd className="font-semibold text-slate-800">MockPANAdapter (VALID)</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">GSTN Status</dt>
                <dd className="font-semibold text-slate-800">MockGSTAdapter (ACTIVE)</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Udyam Registration</dt>
                <dd className="font-semibold text-slate-800">MockUdyamAdapter (ACTIVE)</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Debarment Registry</dt>
                <dd className="font-semibold text-slate-800">MockDebarmentAdapter (PAN lookup)</dd>
              </div>
              <div className="py-2.5 flex justify-between">
                <dt className="text-slate-500">Notice</dt>
                <dd className="text-amber-700 font-semibold">Simulated demo environment</dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Guiding Principles Card */}
        <div className="rounded-2xl border border-brand-100 bg-gradient-to-r from-brand-900 to-navy-950 p-6 text-white shadow-xl">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/10 text-white backdrop-blur-xs">
              <IconFileText className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold">Platform Governance Principle</h3>
              <p className="mt-1 text-sm font-medium text-brand-100">
                &ldquo;AI verifies. Evidence explains. Officer decides.&rdquo;
              </p>
              <p className="mt-2 text-xs text-brand-200/80 leading-relaxed max-w-3xl">
                The platform operates strictly as a decision-support copilot for GeM procurement officers.
                Verdicts and scores are derived through immutable deterministic rules. The LLM extracts data at temperature 0
                and never issues verdicts or replaces officer discretion.
              </p>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
