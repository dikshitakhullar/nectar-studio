"use client";

import { useState } from "react";
import Link from "next/link";
import { StepNav } from "../components/StepNav";
import {
  ART_TECHNIQUES,
  demoArtPieces,
  recommendTechnique,
  type ArtTechnique,
} from "@/lib/studio/art-lighting";

export default function ArtLightingPage() {
  const [picks, setPicks] = useState<Record<string, ArtTechnique>>(() => {
    const init: Record<string, ArtTechnique> = {};
    for (const p of demoArtPieces) init[p.id] = p.initialRecommendation;
    return init;
  });

  return (
    <div className="space-y-10">
      <StepNav currentHref="/studio/art-lighting" />

      <div className="space-y-2">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Art lighting</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">How should we light your art?</h1>
        <p className="text-stone-600 text-sm leading-relaxed max-w-2xl">
          The same piece reads completely differently under each technique. Pick one per art piece and we&apos;ll wire it into the fixture schedule and switching plan.
        </p>
      </div>

      {/* Comparison grid (educational, static) */}
      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">One panel, four techniques</div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {ART_TECHNIQUES.filter((t) => t.imagePath).map((t) => (
            <div key={t.id} className="space-y-2">
              <div className="relative bg-white border border-stone-200 rounded-md overflow-hidden aspect-[3/2]">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={t.imagePath}
                  alt={t.label}
                  className="w-full h-full object-cover"
                />
                <div className="absolute top-2 left-2 bg-white/90 backdrop-blur px-2 py-0.5 rounded text-[10px] uppercase tracking-wider text-stone-700">
                  {t.shortLabel}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium text-stone-900">{t.label}</div>
                <p className="text-[11px] text-stone-500 leading-relaxed mt-0.5">{t.bestFor}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-stone-500 leading-relaxed max-w-2xl">
          Tip: techniques that reveal texture (grazing, spotlight) favour relief and sculpture; flat pieces read fine on grid or spotlight.
        </p>
      </section>

      {/* Per-art-piece picker */}
      <section className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Pieces in this room</div>
        <div className="space-y-4">
          {demoArtPieces.map((piece) => {
            const recommended = recommendTechnique(piece);
            const recommendedTech = ART_TECHNIQUES.find((t) => t.id === recommended)!;
            const picked = picks[piece.id];

            return (
              <div key={piece.id} className="bg-white border border-stone-200 rounded-md p-5 space-y-4">
                <div>
                  <div className="text-sm font-medium text-stone-900">{piece.description}</div>
                  <div className="text-xs text-stone-500 mt-1">
                    {piece.type.replace("_", " ")} · {piece.dimensionality} · {piece.size} · {piece.framed ? "framed" : "unframed"} · {piece.importance}
                  </div>
                </div>

                <div className="border-l-2 border-amber-300 bg-amber-50/50 pl-3 py-2 rounded-r">
                  <div className="text-xs uppercase tracking-wider text-amber-700/90 font-medium">Agent recommends</div>
                  <div className="text-sm text-stone-900 mt-0.5">{recommendedTech.label}</div>
                  <p className="text-xs text-stone-600 mt-1 leading-relaxed">
                    {recommendedTech.oneLiner} {recommendedTech.bestFor}
                  </p>
                </div>

                <div className="space-y-2">
                  <div className="text-xs text-stone-500">Or pick another technique:</div>
                  <div className="flex flex-wrap gap-2">
                    {ART_TECHNIQUES.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setPicks((prev) => ({ ...prev, [piece.id]: t.id }))}
                        className={`text-xs border rounded-full px-3 py-1.5 transition ${
                          picked === t.id
                            ? "border-amber-700 text-amber-700 bg-amber-50 font-medium"
                            : "border-stone-200 text-stone-700 hover:border-stone-400 bg-white"
                        }`}
                      >
                        {t.shortLabel}
                      </button>
                    ))}
                  </div>
                  {picked && picked !== recommended && (
                    <p className="text-[11px] text-stone-500 italic">
                      Overriding the recommendation. We&apos;ll update the fixture schedule accordingly.
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/walls" className="text-sm text-stone-500 hover:text-stone-700">
          ← Back to walls
        </Link>
        <Link
          href="/studio/furniture"
          className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition"
        >
          Continue to furniture →
        </Link>
      </div>
    </div>
  );
}
