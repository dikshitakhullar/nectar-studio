"use client";

import { useMemo, useState } from "react";
import type { Fixture, Room } from "@/lib/studio/types";
import {
  estimateAverageLux,
  estimateUniformity,
  estimateUGR,
  computeAccentRatio,
  floorAreaSqFt,
  getIESStatus,
  getIESTargets,
} from "@/lib/studio/lux-math";

type BadgeTone = "ok" | "warn" | "bad";

function Badge({ tone, children }: { tone: BadgeTone; children: React.ReactNode }) {
  const classes =
    tone === "ok"
      ? "text-emerald-700 bg-emerald-50 border border-emerald-200"
      : tone === "warn"
        ? "text-amber-700 bg-amber-50 border border-amber-200"
        : "text-rose-700 bg-rose-50 border border-rose-200";
  const glyph = tone === "ok" ? "✓" : tone === "warn" ? "⚠" : "✗";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs ${classes}`}>
      <span aria-hidden>{glyph}</span>
      {children}
    </span>
  );
}

function reflectanceForWalls(wallFinish: Room["wallFinish"]): number {
  if (wallFinish === "light") return 0.75;
  if (wallFinish === "dark") return 0.45;
  return 0.65;
}

export function LuxUniformity({ fixtures, room }: { fixtures: Fixture[]; room: Room }) {
  const iesTargets = getIESTargets(room.type, "ambient");
  const defaultTarget = room.targetLuxAmbient ?? iesTargets.recommended;
  const [targetLux, setTargetLux] = useState<number>(defaultTarget);

  const reflectance = reflectanceForWalls(room.wallFinish);
  const floorArea = floorAreaSqFt(room);

  const computedLux = useMemo(
    () => estimateAverageLux(fixtures, floorArea, reflectance),
    [fixtures, floorArea, reflectance],
  );
  const uniformity = useMemo(() => estimateUniformity(fixtures.length), [fixtures]);
  const ugr = useMemo(() => estimateUGR(fixtures), [fixtures]);
  const accent = useMemo(() => computeAccentRatio(fixtures), [fixtures]);
  const iesStatus = useMemo(
    () => getIESStatus(computedLux, room.type, "ambient"),
    [computedLux, room.type],
  );

  // IES tier badge
  const iesTone: BadgeTone =
    iesStatus === "at_or_above_recommended" ? "ok" : iesStatus === "below_recommended" ? "warn" : "bad";
  const iesLabel =
    iesStatus === "at_or_above_recommended"
      ? "meets IES recommended"
      : iesStatus === "below_recommended"
        ? "above IES minimum, below recommended"
        : "BELOW IES MINIMUM";

  // Designer-target badge (separate from IES)
  const meetsDesignerTarget = computedLux >= targetLux * 0.9;
  const designerTone: BadgeTone = meetsDesignerTarget ? "ok" : "warn";
  const designerLabel = meetsDesignerTarget ? "meets your target" : "below your target";

  const uniformityTone: BadgeTone = uniformity <= 2.0 ? "ok" : "warn";
  const uniformityLabel = uniformity <= 2.0 ? "residential-acceptable" : "uneven";

  const ugrTone: BadgeTone = ugr < 19 ? "ok" : ugr <= 22 ? "warn" : "bad";
  const ugrLabel = ugr < 19 ? "< 19 residential threshold" : ugr <= 22 ? "borderline" : "over threshold";

  let accentTone: BadgeTone;
  let accentLabel: string;
  if (accent.ratio >= 3 && accent.ratio <= 5) {
    accentTone = "ok";
    accentLabel = "within 3:1–5:1 target";
  } else if ((accent.ratio >= 1.5 && accent.ratio < 3) || (accent.ratio > 5 && accent.ratio <= 10)) {
    accentTone = "warn";
    accentLabel = accent.ratio < 3 ? "below accent contrast" : "above accent contrast";
  } else {
    accentTone = "bad";
    accentLabel = "outside acceptable range";
  }

  return (
    <div className="bg-white border border-stone-200 rounded-md p-5 space-y-4">
      {/* IES standards reference — fixed, displayed prominently */}
      <div className="bg-stone-50 border border-stone-200 rounded-md p-3 space-y-1.5">
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">IES residential standard</div>
          <a
            href="https://www.ies.org/"
            target="_blank"
            rel="noreferrer"
            className="text-[10px] text-stone-400 hover:text-stone-600 underline-offset-2"
          >
            ies.org →
          </a>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-stone-700">
          <div>
            <span className="text-stone-500">Minimum: </span>
            <span className="font-medium tabular-nums">{iesTargets.minimum} lx</span>
          </div>
          <div>
            <span className="text-stone-500">Recommended: </span>
            <span className="font-medium tabular-nums">{iesTargets.recommended} lx</span>
          </div>
          <div>
            <span className="text-stone-500">High-task / elderly: </span>
            <span className="font-medium tabular-nums">{iesTargets.high} lx</span>
          </div>
        </div>
      </div>

      {/* Target lux slider (designer-override) */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label htmlFor="target-lux" className="text-sm text-stone-700">
            Your target ambient lux
          </label>
          <span className="text-sm text-stone-900 tabular-nums">{targetLux} lx</span>
        </div>
        <input
          id="target-lux"
          type="range"
          min={50}
          max={1000}
          step={10}
          value={targetLux}
          onChange={(e) => setTargetLux(Number(e.target.value))}
          className="w-full accent-amber-700"
        />
        <div className="flex justify-between text-[10px] text-stone-400 tabular-nums">
          <span>50</span>
          <span>1000</span>
        </div>
      </div>

      {/* Indicator rows */}
      <div className="space-y-2 pt-2 border-t border-stone-100">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm text-stone-500">Computed average</div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <span className="text-sm text-stone-900 tabular-nums">{computedLux} lx</span>
            <Badge tone={iesTone}>{iesLabel}</Badge>
            <Badge tone={designerTone}>{designerLabel}</Badge>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="text-sm text-stone-500">Uniformity ratio</div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-stone-900 tabular-nums">{uniformity.toFixed(1)}</span>
            <Badge tone={uniformityTone}>{uniformityLabel}</Badge>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="text-sm text-stone-500">UGR estimate</div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-stone-900 tabular-nums">{ugr}</span>
            <Badge tone={ugrTone}>{ugrLabel}</Badge>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="text-sm text-stone-500">
            Accent ratio
            {accent.brightestAccentTag && (
              <span className="text-xs text-stone-400 ml-1">({accent.brightestAccentTag})</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-stone-900 tabular-nums">{accent.ratio.toFixed(1)} : 1</span>
            <Badge tone={accentTone}>{accentLabel}</Badge>
          </div>
        </div>
      </div>

      <details className="text-xs text-stone-500 pt-2 border-t border-stone-100">
        <summary className="cursor-pointer hover:text-stone-700">
          <span aria-hidden>ⓘ</span> How is this computed and what does IES mean?
        </summary>
        <div className="pt-2 leading-relaxed space-y-2">
          <p>
            <strong>IES (Illuminating Engineering Society)</strong> publishes illuminance recommendations
            for residential and commercial spaces. We use their 3-tier residential model (minimum,
            recommended, high-task) as a non-negotiable floor for plans we generate — no plan ships with
            an ambient lux below the IES minimum for that room type.
          </p>
          <p>
            <strong>Computed lux</strong> is estimated from total fixture lumens divided by floor area,
            with a reflectance factor based on wall finish. <strong>UGR</strong> is a heuristic based on
            fixture types and mounting (visible bright fixtures and narrow-beam wall aim increase glare;
            recessed downlights reduce it). <strong>Uniformity</strong> is approximated from fixture
            count. <strong>Accent ratio</strong> compares the brightest accent fixture&apos;s effective
            output to average ambient. For pixel-accurate photometric simulation, use DIALux.
          </p>
        </div>
      </details>
    </div>
  );
}
