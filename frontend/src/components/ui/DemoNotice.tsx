import React from "react";

/**
 * Spec requirement: every verified-status display must carry this notice so
 * the UI never implies live GSTN/Udyam/PAN access. Render it beside any
 * status badge / compliance profile (Phase 7 dashboard onward).
 */
export function DemoNotice({ className = "" }: { className?: string }) {
  return (
    <div
      className={`rounded-xl border border-amber-300/80 bg-amber-50 px-4 py-3 text-xs text-amber-900 shadow-2xs ${className}`}
    >
      <span className="font-bold">Demo Environment</span> — results simulated
      via mock adapter (MockPANAdapter, MockGSTAdapter, MockUdyamAdapter,
      MockDebarmentAdapter). No live GSTN/Udyam/PAN integration is used.
    </div>
  );
}
