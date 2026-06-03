"use client";

import Link from "next/link";
import { useState } from "react";
import { StepNav } from "../components/StepNav";
import { RenderGallery } from "../components/RenderGallery";
import { LayeredBreakdown } from "../components/LayeredBreakdown";
import { RCPDiagramSVG } from "../components/RCPDiagramSVG";
import { WallElevationSVG } from "../components/WallElevationSVG";
import { FixtureScheduleTable } from "../components/FixtureScheduleTable";
import { SwitchingDiagram } from "../components/SwitchingDiagram";
import { BOQTable } from "../components/BOQTable";
import { BrandRecCard } from "../components/BrandRecCard";
import { NotesList } from "../components/NotesList";
import { IterationChat } from "../components/IterationChat";
import { LuxUniformity } from "../components/LuxUniformity";
import { SceneProgramming } from "../components/SceneProgramming";
import { demoPack } from "@/lib/studio/demo-data";
import { formatInr } from "@/lib/studio/boq";
import { totalWattage } from "@/lib/studio/fixtures";

type TabId = "plan" | "boq" | "notes";

const TABS: { id: TabId; label: string }[] = [
  { id: "plan", label: "Plan & Layout" },
  { id: "boq", label: "BOQ" },
  { id: "notes", label: "Notes" },
];

const WALL_IDS = ["north", "east", "south", "west"] as const;

export default function PackPage() {
  const [tab, setTab] = useState<TabId>("plan");
  const [wallIdx, setWallIdx] = useState(0);
  const wattage = totalWattage(demoPack.fixtures);

  return (
    <div className="space-y-12 max-w-4xl mx-auto">
      <StepNav currentHref="/studio/pack" />

      <header className="space-y-3 border-b border-stone-200 pb-8">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Lighting Plan</div>
        <div>
          <h1 className="text-3xl font-light tracking-tight text-stone-900">{demoPack.projectProfile.clientName}</h1>
          <div className="text-sm text-stone-500 mt-1">{demoPack.projectProfile.projectName} · Living / TV Room · 12 × 15 ft</div>
        </div>
        <div className="flex gap-6 text-sm text-stone-600 pt-2 flex-wrap">
          <div><span className="text-stone-400">Fixtures</span> <span className="text-stone-900">{demoPack.fixtures.length}</span></div>
          <div><span className="text-stone-400">Wattage</span> <span className="text-stone-900">{wattage} W</span></div>
          <div><span className="text-stone-400">BOQ</span> <span className="text-stone-900">{formatInr(demoPack.totals.grandTotalInr)}</span></div>
          <div><span className="text-stone-400">Est. monthly</span> <span className="text-stone-900">{formatInr(demoPack.totals.estMonthlyEnergyInr)}</span></div>
        </div>
      </header>

      {/* HERO — always visible, dominant */}
      <section className="space-y-12">
        <div>
          <div className="text-xs uppercase tracking-wider text-amber-700/90 mb-4">Renders</div>
          <RenderGallery />
        </div>

        <div className="space-y-4">
          <div className="text-xs uppercase tracking-wider text-amber-700/90 mb-4">Design intent</div>
          <div className="text-stone-700 whitespace-pre-line text-sm leading-relaxed space-y-3">
            {demoPack.narrative}
          </div>
          <div className="border-l-2 border-amber-300 bg-amber-50/50 pl-4 pr-3 py-3 rounded-r">
            <div className="text-xs uppercase tracking-wider text-amber-700/90 font-medium">Wellbeing considered</div>
            <p className="text-xs text-stone-600 leading-relaxed mt-1.5">
              All decoratives and cove are 2700K to protect evening melatonin. Architectural fixtures spec&apos;d at CRI 90+ for colour comfort. Layered scenes (Daytime / Conversation / Cinema / Dramatic) give the room emotional range without rewiring. Lux targets are conservative against glare; spots are dimmable for accent-only evening moods.
            </p>
          </div>
        </div>

        <div>
          <div className="text-xs uppercase tracking-wider text-amber-700/90 mb-4">Layered lighting</div>
          <LayeredBreakdown fixtures={demoPack.fixtures} />
        </div>
      </section>

      {/* TABS */}
      <div>
        <div className="flex gap-6 border-b border-stone-200 mb-8 sticky top-0 bg-stone-50 z-10 pt-2">
          {TABS.map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`pb-3 text-sm font-medium transition border-b-2 -mb-px ${
                tab === t.id
                  ? "text-amber-700 border-amber-700"
                  : "text-stone-500 border-transparent hover:text-stone-900 hover:border-stone-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "plan" && (
          <div className="space-y-12">
            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">Lighting on your RCP</div>
              <RCPDiagramSVG />
              <p className="text-xs text-stone-500">Fixture positions placed on your reflected ceiling plan. Yellow = ambient, rose = accent, violet = decorative. Dashed perimeter is the cove.</p>
            </section>

            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">Lux & uniformity</div>
              <LuxUniformity fixtures={demoPack.fixtures} room={demoPack.room} />
            </section>

            <section className="space-y-4">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="text-xs uppercase tracking-wider text-amber-700/90">Wall elevations</div>
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    {WALL_IDS.map((w, i) => (
                      <button
                        key={w}
                        type="button"
                        onClick={() => setWallIdx(i)}
                        className={`px-3 py-1 text-xs rounded-full border transition capitalize ${
                          wallIdx === i
                            ? "border-amber-700 text-amber-700 bg-amber-50"
                            : "border-stone-200 text-stone-500 hover:border-stone-400 bg-white"
                        }`}
                      >
                        {w}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1 ml-1">
                    <button
                      type="button"
                      onClick={() => setWallIdx(Math.max(0, wallIdx - 1))}
                      disabled={wallIdx === 0}
                      className="border border-stone-200 bg-white rounded-md w-7 h-7 text-stone-500 hover:border-stone-400 disabled:opacity-30 disabled:cursor-not-allowed transition"
                      aria-label="Previous wall"
                    >
                      ←
                    </button>
                    <button
                      type="button"
                      onClick={() => setWallIdx(Math.min(WALL_IDS.length - 1, wallIdx + 1))}
                      disabled={wallIdx === WALL_IDS.length - 1}
                      className="border border-stone-200 bg-white rounded-md w-7 h-7 text-stone-500 hover:border-stone-400 disabled:opacity-30 disabled:cursor-not-allowed transition"
                      aria-label="Next wall"
                    >
                      →
                    </button>
                  </div>
                </div>
              </div>
              <div className="overflow-hidden">
                <div
                  className="flex transition-transform duration-300 ease-out"
                  style={{ transform: `translateX(-${wallIdx * 100}%)` }}
                >
                  {WALL_IDS.map(w => (
                    <div key={w} className="min-w-full pr-0">
                      <WallElevationSVG wallId={w} />
                    </div>
                  ))}
                </div>
              </div>
              <div className="text-xs text-stone-500 text-center">
                Wall {wallIdx + 1} of {WALL_IDS.length}
              </div>
            </section>

            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">Fixture schedule</div>
              <FixtureScheduleTable fixtures={demoPack.fixtures} />
            </section>

            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">Switching + dimming</div>
              <SwitchingDiagram zones={demoPack.switching} />
            </section>

            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">Scene programming</div>
              <SceneProgramming scenes={demoPack.scenes} fixtures={demoPack.fixtures} />
            </section>
          </div>
        )}

        {tab === "boq" && (
          <div className="space-y-12">
            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">BOQ</div>
              <BOQTable lines={demoPack.boq} />
            </section>

            <section className="space-y-4">
              <div className="text-xs uppercase tracking-wider text-amber-700/90">Brand picks (architectural)</div>
              <p className="text-xs text-stone-500">Decorative picks come from our curated partner catalogs. Architectural picks per budget tier:</p>
              <BrandRecCard fixtures={demoPack.fixtures} />
            </section>
          </div>
        )}

        {tab === "notes" && (
          <div className="space-y-12">
            <NotesList title="Application notes" items={demoPack.applicationNotes} />
            <NotesList title="Installation notes" items={demoPack.installationNotes} />
          </div>
        )}
      </div>

      {/* Iteration chat — always visible, below tabs */}
      <section className="space-y-4">
        <IterationChat />
      </section>

      <div className="border-t border-stone-200 pt-6">
        <Link href="/studio/brief" className="text-sm text-stone-500 hover:text-stone-700">← Back to brief</Link>
      </div>
    </div>
  );
}
