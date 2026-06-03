const OPTIONS = [
  {
    id: "option-2-watercolor",
    label: "Watercolor A — Lit living room (original)",
    description: "Warm watercolor wash of the lit living room. Brass pendant glowing, picture lights on art, morning window light.",
    feel: "Warm / inviting / human.",
  },
  {
    id: "option-2b-watercolor-wide",
    label: "Watercolor B — Wider view, layered light",
    description: "Wider room showing all 4 layers in harmony: cove glow, downlight pools, pendant, picture lights. Light interplay is the hero.",
    feel: "Atmospheric / shows the full layered story.",
  },
  {
    id: "option-2c-watercolor-detail",
    label: "Watercolor C — Intimate detail",
    description: "Close-up of brass pendant over coffee table with a sketchbook + coffee cup. Warm light pool on the table.",
    feel: "Intimate / 'designer at the table' / process-oriented.",
  },
  {
    id: "option-3-flat-vector",
    label: "Flat vector A — Designer's desk (original)",
    description: "Top-down desk with floor plan blueprint, brass desk lamp, plant, coffee. Procurist-adjacent.",
    feel: "Tool-for-designers / process / quiet.",
  },
  {
    id: "option-3b-flat-vector-room",
    label: "Flat vector B — Lit room (output)",
    description: "Three-quarter view of the lit living room in flat vector style. Brass pendant, picture lights, cove glow.",
    feel: "Shows-the-output / aspirational / minimal.",
  },
  {
    id: "option-3c-flat-vector-designer-room",
    label: "Flat vector C — Designer + room (split scene)",
    description: "Split: designer at drafting table on the left, the resulting lit room on the right. 'Your vision, realized.'",
    feel: "Narrative / process + output / human + product.",
  },
];

export default function LandingOptionsPreview() {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 px-6 py-10">
      <div className="max-w-5xl mx-auto space-y-10">
        <header className="space-y-2">
          <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Pick one</div>
          <h1 className="text-3xl font-light tracking-tight text-stone-900">Landing illustration options</h1>
          <p className="text-stone-600 text-sm leading-relaxed">
            Four styles for the hero illustration on <a href="/studio" className="text-amber-700 underline">/studio</a>. Each is a different visual register — tell me which one feels right (or none, and we iterate).
          </p>
        </header>

        <div className="space-y-12">
          {OPTIONS.map((opt) => (
            <section key={opt.id} className="space-y-4">
              <div>
                <h2 className="text-xl font-light tracking-tight text-stone-900">{opt.label}</h2>
                <p className="text-sm text-stone-600 mt-1 leading-relaxed">{opt.description}</p>
                <p className="text-xs text-amber-700 mt-1 italic">{opt.feel}</p>
              </div>
              <div className="bg-white border border-stone-200 rounded-md overflow-hidden">
                <img
                  src={`/studio/landing-options/${opt.id}.jpg`}
                  alt={opt.label}
                  className="w-full h-auto"
                />
              </div>
            </section>
          ))}
        </div>

        <footer className="border-t border-stone-200 pt-6">
          <p className="text-sm text-stone-600">
            Tell me which option (or describe a different direction) and I&apos;ll wire it into the landing page.
          </p>
        </footer>
      </div>
    </div>
  );
}
