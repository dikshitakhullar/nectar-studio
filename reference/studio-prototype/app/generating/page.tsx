"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LightingTip } from "../components/LightingTip";

const STEPS = [
  "Reading your project profile…",
  "Mapping room geometry and orientation…",
  "Computing ambient lux targets for evening lounging…",
  "Picking decorative fixtures from our partner catalogs…",
  "Speccing architectural fixtures and selecting brand picks…",
  "Laying out the reflected ceiling plan…",
  "Drafting switching zones and dimming groups…",
  "Composing photoreal renders — day, evening, mood…",
  "Assembling your Lighting Pack…",
];

export default function GeneratingPage() {
  const [stepIndex, setStepIndex] = useState(0);
  const router = useRouter();

  useEffect(() => {
    if (stepIndex >= STEPS.length) {
      const t = setTimeout(() => router.push("/studio/pack"), 600);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setStepIndex(i => i + 1), 700);
    return () => clearTimeout(t);
  }, [stepIndex, router]);

  return (
    <div className="space-y-10 py-12 min-h-[60vh] flex flex-col justify-center">
      <div className="space-y-3 text-center">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Studio at work</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Designing your room…</h1>
      </div>
      <ul className="max-w-md mx-auto w-full space-y-2">
        {STEPS.map((s, i) => (
          <li
            key={i}
            className={`text-sm transition-opacity duration-300 flex items-center gap-2 ${
              i < stepIndex ? "text-stone-400 line-through" : i === stepIndex ? "text-amber-700" : "text-stone-300"
            }`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
            {s}
          </li>
        ))}
      </ul>

      <div className="max-w-md mx-auto w-full pt-6">
        <LightingTip rotateEveryMs={6000} compact />
      </div>
    </div>
  );
}
