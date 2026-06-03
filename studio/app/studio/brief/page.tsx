"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, OptionGroup, Spinner } from "../components/UIPrimitives";
import { ApiError, postBrief } from "@/lib/api/client";
import type { Mood, TimeOfDay } from "@/lib/api/types";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

const MOOD_OPTIONS: { id: Mood; label: string; description?: string }[] = [
  { id: "cozy", label: "Cozy", description: "Soft, warm, restful" },
  { id: "productive", label: "Productive", description: "Bright, clear, energising" },
  { id: "wind_down", label: "Wind down", description: "Low, indirect, melatonin-friendly" },
  { id: "entertain", label: "Entertain", description: "Layered, dramatic, accent-heavy" },
];

const TIME_OPTIONS: { id: TimeOfDay; label: string }[] = [
  { id: "morning", label: "Morning" },
  { id: "evening", label: "Evening" },
  { id: "late_night", label: "Late night" },
];

export default function BriefPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [mood, setMood] = useState<Mood | null>(null);
  const [timeOfUse, setTimeOfUse] = useState<TimeOfDay[]>([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pid || !rid) return;
    setSubmitting(true);
    setError(null);
    try {
      await postBrief(pid, rid, {
        intent_mood: mood,
        time_of_use: timeOfUse,
        notes,
      });
      router.push(`/studio/generating?${buildStudioQuery(pid, rid)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not save brief.");
      }
      setSubmitting(false);
    }
  };

  if (!pid || !rid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/brief" />
        <ErrorBanner message="Missing project or room id. Start from upload." />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/brief" query={buildStudioQuery(pid, rid)} />

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Brief</h1>
        <p className="text-stone-600 text-sm">
          Mood and usage time. The engine uses both to pick CCT, layer balance,
          and dimming defaults.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      <form onSubmit={onSubmit} className="space-y-8">
        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Mood</div>
          <OptionGroup
            options={MOOD_OPTIONS}
            value={mood ? [mood] : []}
            onChange={(next) => setMood((next[0] as Mood) ?? null)}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">When is this room used?</div>
          <OptionGroup
            options={TIME_OPTIONS}
            multi
            value={timeOfUse}
            onChange={(next) => setTimeOfUse(next as TimeOfDay[])}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Anything else? (optional)</div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="e.g. 'highlight a painting on the west wall' or 'no exposed downlights'"
            className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
          />
        </section>

        <div className="flex justify-between pt-6 border-t border-stone-200">
          <Link
            href={`/studio/furniture?${buildStudioQuery(pid, rid)}`}
            className="text-sm text-stone-500 hover:text-stone-700"
          >
            ← Back
          </Link>
          {submitting ? (
            <Spinner label="Saving brief…" />
          ) : (
            <button
              type="submit"
              className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition"
            >
              Generate my lighting plan →
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
