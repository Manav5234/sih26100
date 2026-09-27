import Link from "next/link";
import { Logo } from "@/components/brand/Logo";
import { IconArrowRight, IconFileText, IconShield, IconAI } from "@/components/ui/Icons";
import { DemoNotice } from "@/components/ui/DemoNotice";

const STEPS = [
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
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-500 transition-colors"
          >
            Officer Sign In
            <IconArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-16">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-brand-400/30 bg-brand-500/10 px-3 py-1 text-xs font-semibold text-brand-300">
            GeM Procurement Compliance
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

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.title} className="rounded-2xl border border-slate-800 bg-slate-950/60 p-5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-brand-500/20 bg-brand-500/10 text-brand-400">
                {s.icon}
              </div>
              <h2 className="mt-4 text-sm font-bold text-white">{s.title}</h2>
              <p className="mt-2 text-xs leading-relaxed text-slate-400">{s.body}</p>
            </div>
          ))}
        </div>

        <DemoNotice className="mt-10" />
      </main>

      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500">
        SIH26100 • Bid Compliance Verification Platform
      </footer>
    </div>
  );
}
