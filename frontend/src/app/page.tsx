import Link from "next/link";
import { Logo } from "@/components/brand/Logo";
import {
  IconArrowRight,
  IconFileText,
  IconShield,
  IconAI,
  IconUsers,
} from "@/components/ui/Icons";
import { DemoNotice } from "@/components/ui/DemoNotice";

const WORKFLOW_STEPS = [
  {
    icon: <IconFileText className="h-4 w-4" />,
    title: "Tender → Requirements",
    body: "Clauses from the tender PDF are extracted into a structured checklist, each mapped to an existing rule with its legal source.",
  },
  {
    icon: <IconAI className="h-4 w-4" />,
    title: "Evidence → Verification",
    body: "Bidder documents are read, fields extracted with page-level evidence, identity cross-checked, and evaluated by a deterministic rule engine.",
  },
  {
    icon: <IconShield className="h-4 w-4" />,
    title: "Recommendation → Decision",
    body: "The system reports a verdict, score, risk and recommendation. Only a Procurement Officer records a final decision.",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen bg-navy-950 text-slate-200">
      <header className="border-b border-slate-800/80">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Logo size="md" variant="light" href="/" />
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-16">
        {/* Hero */}
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-400/30 bg-brand-500/10 px-3 py-1 text-xs font-semibold text-brand-300">
            GeM Procurement Compliance Platform
          </span>
          <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
            AI verifies. Evidence explains. Officer decides.
          </h1>
          <p className="mt-5 text-sm leading-relaxed text-slate-400 sm:text-base">
            A tender-aware compliance verification workspace. Every finding is traceable to a
            source document, page, extracted value and the rule that produced it — and the
            system never qualifies or disqualifies a bidder on its own.
          </p>
        </div>

        {/* Entry Points — two clearly separated portals */}
        <div className="mt-12 grid gap-5 sm:grid-cols-2 max-w-3xl">
          {/* Officer Portal */}
          <div className="group relative flex flex-col rounded-2xl border border-brand-500/30 bg-brand-500/5 p-6 hover:border-brand-400/60 hover:bg-brand-500/10 transition-all">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-brand-500/20 bg-brand-500/10">
              <IconShield className="h-5 w-5 text-brand-400" />
            </div>
            <h2 className="mt-4 text-lg font-extrabold text-white">
              Procurement Officer
            </h2>
            <p className="mt-1 text-sm text-slate-400 flex-1">
              Full procurement compliance workspace — tender upload, bidder management, evidence review, and final decisions.
            </p>
            <div className="mt-4 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Authentication required
            </div>
            <Link
              href="/login"
              className="mt-3 inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-brand-500 transition-colors"
            >
              Officer Sign In
              <IconArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {/* Bidder Self-Check Portal */}
          <div className="group relative flex flex-col rounded-2xl border border-slate-700/60 bg-slate-900/40 p-6 hover:border-slate-600 hover:bg-slate-900/60 transition-all">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-600/30 bg-slate-800/50">
              <IconUsers className="h-5 w-5 text-slate-400" />
            </div>
            <h2 className="mt-4 text-lg font-extrabold text-white">
              Bidder Self-Check
            </h2>
            <p className="mt-1 text-sm text-slate-400 flex-1">
              Non-authoritative document readiness check — upload your PAN, GST and Udyam documents to identify potential issues before submission.
            </p>
            <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-1.5 text-[11px] text-amber-400 font-medium">
              Pre-submission self-check — not an authoritative procurement decision.
            </div>
            <Link
              href="/self-check"
              className="mt-3 inline-flex items-center justify-center gap-2 rounded-xl border border-slate-600 bg-slate-800 px-4 py-2.5 text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white transition-colors"
            >
              Start Self-Check
              <IconArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>

        {/* How it works */}
        <div className="mt-14">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500 mb-5">
            How it works
          </p>
          <div className="grid gap-4 md:grid-cols-3">
            {WORKFLOW_STEPS.map((s) => (
              <div key={s.title} className="rounded-2xl border border-slate-800 bg-slate-950/60 p-5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-brand-500/20 bg-brand-500/10 text-brand-400">
                  {s.icon}
                </div>
                <h2 className="mt-4 text-sm font-bold text-white">{s.title}</h2>
                <p className="mt-2 text-xs leading-relaxed text-slate-400">{s.body}</p>
              </div>
            ))}
          </div>
        </div>

        <DemoNotice className="mt-10" />
      </main>

      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500">
        SIH26100 • Bid Compliance Verification Platform
      </footer>
    </div>
  );
}
