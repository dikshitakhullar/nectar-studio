import Link from "next/link";
import { LightingTip } from "./components/LightingTip";

export default function StudioLandingPage() {
  return (
    <div className="space-y-16">
      {/* HERO — text first, agent portrait alongside */}
      <section className="grid sm:grid-cols-[1fr_auto] gap-8 items-center">
        <div className="space-y-6">
          <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Prototype</div>
          <h1 className="text-4xl font-light tracking-tight text-stone-900 leading-tight">
            Meet your lighting design agent.
          </h1>
          <p className="text-lg text-stone-600 leading-relaxed">
            Turn floor plans and briefs into photoreal renders, fixture schedules, switching diagrams, and costed BOQs — in minutes. Built for how interior design studios actually work.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link href="/studio/upload" className="inline-flex items-center gap-2 bg-amber-700 text-white px-5 py-3 rounded-md font-medium hover:bg-amber-800 transition shadow-sm">
              Upload your project files →
            </Link>
            <Link href="/studio/project-profile" className="inline-flex items-center gap-2 border border-stone-300 text-stone-700 px-5 py-3 rounded-md font-medium hover:border-stone-500 transition">
              Or walk through wall by wall
            </Link>
          </div>
        </div>
        {/* Agent portrait — Procurist-style stylized character */}
        <div className="hidden sm:block w-44 lg:w-56 shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/studio/agent-portrait.jpg"
            alt="Your lighting design agent"
            className="w-full h-auto rounded-md shadow-sm"
          />
        </div>
      </section>

      {/* Hero illustration — AFTER the text */}
      <div className="bg-white border border-stone-200 rounded-md overflow-hidden shadow-sm">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/studio/landing-options/option-2-watercolor.jpg"
          alt=""
          className="w-full h-auto block"
        />
      </div>

      {/* The problem — designer-side framing, no blame */}
      <section className="space-y-4">
        <h2 className="text-2xl font-light tracking-tight text-stone-900">The lighting layer that goes on top of everything else.</h2>
        <p className="text-stone-600 leading-relaxed max-w-2xl">
          By the time lighting comes up on a project, the ceiling plan is drawn and the furniture layout is mostly placed. What&apos;s still missing is the lighting design that goes on top — which fixtures fit where the ceiling cut-outs already are, how the four layers (ambient / task / accent / decorative) work together, and how it all plays with the furniture below. That&apos;s the gap, and it usually lands on you with no time to do it well.
        </p>
        <div className="grid sm:grid-cols-3 gap-4 pt-4">
          <div className="space-y-1">
            <div className="text-2xl font-light text-amber-700">30+ hrs</div>
            <div className="text-xs text-stone-500 leading-relaxed">per project on fixture selection, sourcing, and BOQ admin</div>
          </div>
          <div className="space-y-1">
            <div className="text-2xl font-light text-amber-700">5+ documents</div>
            <div className="text-xs text-stone-500 leading-relaxed">to add on top of the architectural set — fixture schedule, switching, BOQ, scene programming, install notes</div>
          </div>
          <div className="space-y-1">
            <div className="text-2xl font-light text-amber-700">Most projects</div>
            <div className="text-xs text-stone-500 leading-relaxed">ship with under-layered lighting — one or two layers where four were needed</div>
          </div>
        </div>
      </section>

      {/* How it works — Alya-inspired four-stage */}
      <section className="space-y-6">
        <h2 className="text-2xl font-light tracking-tight text-stone-900">How it works.</h2>
        <ol className="space-y-5">
          <li className="grid grid-cols-[auto_1fr] gap-4 items-baseline">
            <div className="text-xs uppercase tracking-wider text-amber-700/90 w-6">01</div>
            <div>
              <div className="text-sm font-medium text-stone-900">Upload what you already have</div>
              <p className="text-sm text-stone-600 mt-1">Ceiling plan / RCP, furniture layout, electrical, HVAC, 3D renders. We layer lighting on top of what&apos;s already drawn.</p>
            </div>
          </li>
          <li className="grid grid-cols-[auto_1fr] gap-4 items-baseline">
            <div className="text-xs uppercase tracking-wider text-amber-700/90 w-6">02</div>
            <div>
              <div className="text-sm font-medium text-stone-900">Confirm the room</div>
              <p className="text-sm text-stone-600 mt-1">Wall-by-wall, briefly — so we get it right. Skip if you uploaded 3D renders.</p>
            </div>
          </li>
          <li className="grid grid-cols-[auto_1fr] gap-4 items-baseline">
            <div className="text-xs uppercase tracking-wider text-amber-700/90 w-6">03</div>
            <div>
              <div className="text-sm font-medium text-stone-900">Get the lighting design layer</div>
              <p className="text-sm text-stone-600 mt-1">Fixtures placed on your RCP, fixture schedule, switching, scene programming, costed BOQ, photoreal renders — generated in minutes.</p>
            </div>
          </li>
          <li className="grid grid-cols-[auto_1fr] gap-4 items-baseline">
            <div className="text-xs uppercase tracking-wider text-amber-700/90 w-6">04</div>
            <div>
              <div className="text-sm font-medium text-stone-900">Iterate freely</div>
              <p className="text-sm text-stone-600 mt-1">Swap a fixture. Change CCT. Drop the cove. Re-generate in seconds.</p>
            </div>
          </li>
        </ol>
      </section>

      {/* What you get */}
      <section className="space-y-6">
        <h2 className="text-2xl font-light tracking-tight text-stone-900">What you get.</h2>
        <p className="text-stone-600 leading-relaxed max-w-2xl">
          The lighting layer that goes on top of your architectural set. Fixtures specified, positions confirmed, scenes programmed, BOQ costed — plus the photoreal renders a real consultant can&apos;t produce.
        </p>
        <div className="grid sm:grid-cols-2 gap-3 pt-2">
          <div className="bg-white border border-stone-200 rounded-md p-4">
            <div className="text-sm font-medium text-stone-900">Photoreal renders</div>
            <p className="text-xs text-stone-500 mt-1">Day, evening, mood — three scenes per room. The client-ready visuals you can&apos;t get from SketchUp.</p>
          </div>
          <div className="bg-white border border-stone-200 rounded-md p-4">
            <div className="text-sm font-medium text-stone-900">Design intent + layered breakdown</div>
            <p className="text-xs text-stone-500 mt-1">A short narrative explaining the four lighting layers and the choices per layer.</p>
          </div>
          <div className="bg-white border border-stone-200 rounded-md p-4">
            <div className="text-sm font-medium text-stone-900">Fixtures placed on your RCP + wall elevations</div>
            <p className="text-xs text-stone-500 mt-1">Lighting positions marked on the ceiling plan you brought (or one we generate if needed), plus per-wall elevations with sconces, picture lights, art positions.</p>
          </div>
          <div className="bg-white border border-stone-200 rounded-md p-4">
            <div className="text-sm font-medium text-stone-900">Fixture schedule + switching diagram</div>
            <p className="text-xs text-stone-500 mt-1">Tag, qty, wattage, CCT, CRI, beam angle per fixture. Dimming zones and switch locations mapped.</p>
          </div>
          <div className="bg-white border border-stone-200 rounded-md p-4">
            <div className="text-sm font-medium text-stone-900">Costed BOQ with brand picks</div>
            <p className="text-xs text-stone-500 mt-1">Categorized line items, totals, and brand recommendations per architectural category at your budget tier — Wipro, Philips, Astera, Goldmedal.</p>
          </div>
          <div className="bg-white border border-stone-200 rounded-md p-4">
            <div className="text-sm font-medium text-stone-900">Application + installation notes</div>
            <p className="text-xs text-stone-500 mt-1">Why each fixture is placed where it is, and what your electrician needs to know.</p>
          </div>
        </div>
      </section>

      {/* Three moods, one room */}
      <section className="space-y-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-light tracking-tight text-stone-900">Three moods. One room.</h2>
          <p className="text-stone-600 leading-relaxed max-w-2xl">
            Send us your 3D render or floor plan — we&apos;ll show the same room in three lighting moods, with the right fixtures dimmed to the right levels. Natural for daytime, relax for evenings, entertain for hosting.
          </p>
          <p className="text-stone-500 text-sm leading-relaxed max-w-2xl">
            Each mood is a working scene in the Lighting Pack — your electrician can program it directly into the dimmers.
          </p>
        </div>
        <div className="grid sm:grid-cols-3 gap-4 pt-2">
          {[
            { id: "day", label: "Natural", caption: "Daylight-driven. Cove and accents off. Awake, fresh, productive." },
            { id: "evening", label: "Relax", caption: "Warm pendant glow + cove perimeter. Conversation and wind-down." },
            { id: "mood", label: "Entertain", caption: "Accent-heavy. Art wall hero. Dramatic and cinematic." },
          ].map(m => (
            <div key={m.id} className="space-y-3">
              <div className="bg-white border border-stone-200 rounded-md overflow-hidden shadow-sm">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`/studio/renders/${m.id}.jpg`}
                  alt={m.label}
                  className="w-full h-auto block aspect-[4/3] object-cover"
                />
              </div>
              <div>
                <div className="text-xs uppercase tracking-wider text-amber-700/90">{m.label}</div>
                <p className="text-xs text-stone-600 mt-1 leading-relaxed">{m.caption}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Secondary illustration — desk */}
      <div className="bg-white border border-stone-200 rounded-md overflow-hidden shadow-sm">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/studio/landing-options/option-watercolor-desk.jpg"
          alt=""
          className="w-full h-auto block"
        />
      </div>

      {/* Rotating lighting tip */}
      <section className="space-y-3">
        <h2 className="text-xs uppercase tracking-wider text-amber-700/90">Did you know?</h2>
        <LightingTip />
      </section>

      {/* Final CTA */}
      <section className="space-y-4 bg-amber-50 border border-amber-200 rounded-md p-6">
        <h2 className="text-xl font-light tracking-tight text-stone-900">Try it on the demo room.</h2>
        <p className="text-sm text-stone-600 max-w-2xl">
          This prototype walks you through a hardcoded project — the Sharma penthouse, a 12 × 15 ft living/TV room in Vasant Vihar. See the full flow end-to-end, then tell us where it works and where it doesn&apos;t.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Link href="/studio/upload" className="inline-flex items-center gap-2 bg-amber-700 text-white px-5 py-3 rounded-md font-medium hover:bg-amber-800 transition shadow-sm">
            Upload your project files →
          </Link>
          <Link href="/studio/project-profile" className="inline-flex items-center gap-2 border border-stone-300 text-stone-700 px-5 py-3 rounded-md font-medium hover:border-stone-500 transition bg-white">
            Or walk through wall by wall
          </Link>
        </div>
      </section>

      <div className="border-t border-stone-200 pt-6 text-xs text-stone-500 leading-relaxed">
        Prototype mode — built for designer interviews. Real per-project consultations ship in v1.
      </div>
    </div>
  );
}
