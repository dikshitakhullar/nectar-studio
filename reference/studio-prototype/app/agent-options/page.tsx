const OPTIONS = [
  {
    id: "agent-cartoon-line",
    label: "Cartoon line",
    description: "Hand-drawn pen-line with sparse color washes. Confident sketch, New Yorker-ish.",
    feel: "Editorial / handcrafted / sketchbook.",
  },
  {
    id: "agent-flat-vector",
    label: "Flat vector",
    description: "Clean flat shapes, simple character, Procurist/Notion mascot vibe.",
    feel: "Modern / friendly / SaaS-product.",
  },
];

export default function AgentOptionsPreview() {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 px-6 py-10">
      <div className="max-w-4xl mx-auto space-y-10">
        <header className="space-y-2">
          <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Pick one</div>
          <h1 className="text-3xl font-light tracking-tight text-stone-900">Agent illustration options</h1>
          <p className="text-stone-600 text-sm leading-relaxed">
            Both more cartoonish than the previous watercolor portrait. Tell me which feels right (or none, and we iterate).
          </p>
        </header>

        <div className="grid sm:grid-cols-2 gap-8">
          {OPTIONS.map((opt) => (
            <section key={opt.id} className="space-y-4">
              <div className="bg-white border border-stone-200 rounded-md overflow-hidden">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/studio/agent-options/${opt.id}.jpg`}
                  alt={opt.label}
                  className="w-full h-auto"
                />
              </div>
              <div>
                <div className="text-sm font-medium text-stone-900">{opt.label}</div>
                <p className="text-xs text-stone-600 mt-1 leading-relaxed">{opt.description}</p>
                <p className="text-xs text-amber-700 mt-1 italic">{opt.feel}</p>
              </div>
            </section>
          ))}
        </div>

        <footer className="border-t border-stone-200 pt-6">
          <p className="text-sm text-stone-600">
            Tell me which (cartoon line / flat vector / neither — try X instead) and I&apos;ll wire it in.
          </p>
        </footer>
      </div>
    </div>
  );
}
