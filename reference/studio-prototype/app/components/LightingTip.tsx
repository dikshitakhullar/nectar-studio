"use client";

import { useEffect, useState } from "react";
import { LIGHTING_TIPS } from "@/lib/studio/lighting-tips";

interface Props {
  /** Auto-rotate every N ms. Set to 0 to disable rotation. Default 12000 (12s). */
  rotateEveryMs?: number;
  /** Compact variant (smaller padding, no nav arrows). */
  compact?: boolean;
  /** Optional initial topic filter (e.g. "Controls" — only show tips from that topic). */
  topic?: string;
}

export function LightingTip({ rotateEveryMs = 12000, compact = false, topic }: Props) {
  const pool = topic ? LIGHTING_TIPS.filter(t => t.topic === topic) : LIGHTING_TIPS;
  // Stable random start so SSR + hydration don't mismatch — pick on mount only.
  const [index, setIndex] = useState(0);
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    setHasMounted(true);
    setIndex(Math.floor(Math.random() * pool.length));
  }, [pool.length]);

  useEffect(() => {
    if (!hasMounted || rotateEveryMs <= 0) return;
    const t = setInterval(() => {
      setIndex(i => (i + 1) % pool.length);
    }, rotateEveryMs);
    return () => clearInterval(t);
  }, [hasMounted, rotateEveryMs, pool.length]);

  const tip = pool[index];
  if (!tip) return null;

  const next = () => setIndex(i => (i + 1) % pool.length);
  const prev = () => setIndex(i => (i - 1 + pool.length) % pool.length);

  return (
    <div
      className={`bg-white border border-stone-200 rounded-md ${compact ? "p-4" : "p-5"} space-y-2`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">
          Lighting tip · <span className="text-stone-500">{tip.topic}</span>
        </div>
        {!compact && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={prev}
              className="text-stone-400 hover:text-stone-700 px-2 py-1 text-xs"
              aria-label="Previous tip"
            >
              ←
            </button>
            <button
              type="button"
              onClick={next}
              className="text-stone-400 hover:text-stone-700 px-2 py-1 text-xs"
              aria-label="Next tip"
            >
              →
            </button>
          </div>
        )}
      </div>
      <div>
        <div className={`text-stone-900 font-medium ${compact ? "text-sm" : "text-base"}`}>
          {tip.title}
        </div>
        <p
          className={`text-stone-600 leading-relaxed mt-1 ${compact ? "text-xs" : "text-sm"}`}
        >
          {tip.body}
        </p>
      </div>
    </div>
  );
}
