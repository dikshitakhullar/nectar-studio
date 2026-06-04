"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, OptionGroup, Spinner } from "../components/UIPrimitives";
import { ApiError, getRoom, postFurniture } from "@/lib/api/client";
import type { ConfirmedRoom, Furniture, RoomType } from "@/lib/api/types";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

/**
 * Activity vocabulary — Indian residential layered-lighting brief inputs.
 * The id is what we POST (free-form string in the schema's `activities`
 * array); the label is what the designer sees.
 */
const ACTIVITY_OPTIONS: { id: string; label: string }[] = [
  { id: "dining", label: "Dining" },
  { id: "family TV", label: "Family TV" },
  { id: "reading", label: "Reading" },
  { id: "conversation", label: "Conversation" },
  { id: "entertaining", label: "Entertaining" },
  { id: "kids play", label: "Kids play" },
  { id: "work / WFH", label: "Work / WFH" },
  { id: "prayer", label: "Prayer" },
  { id: "naps", label: "Naps" },
  { id: "mood lighting", label: "Mood lighting" },
  { id: "meditation", label: "Meditation" },
];

/**
 * Default activity selections per confirmed room type. Pulled from the
 * Indian-residential layered-lighting vocab the LLM brief layer is tuned
 * against; the designer can edit any of these before submitting.
 *
 * Room types that aren't in this map fall back to no defaults — that's
 * deliberate; "unknown" or generic rooms shouldn't bias the brief.
 */
const ACTIVITY_DEFAULTS: Partial<Record<RoomType, string[]>> = {
  dining: ["dining"],
  living: ["entertaining", "conversation", "family TV"],
  bedroom: ["reading", "naps", "mood lighting"],
  study: ["work / WFH", "reading"],
  kitchen: ["dining"],
};

/** Render a Furniture record as the read-only list item. */
function furnitureLabel(f: Furniture): string {
  const type = f.type && f.type !== "unknown" ? f.type : "furniture";
  const raw = f.raw_label;
  return raw && raw.length > 0 ? `${type} (${raw})` : type;
}

export default function FurniturePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [room, setRoom] = useState<ConfirmedRoom | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activities, setActivities] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id. Start from upload.");
      return;
    }
    setError(null);
    try {
      const r = await getRoom(pid, rid);
      setRoom(r);
      // Pre-fill: if the user already saved activities, use those.
      // Otherwise apply room-type defaults so the form isn't blank.
      const stored = r.activities ?? [];
      if (stored.length > 0) {
        setActivities(stored);
      } else {
        const typeKey: RoomType = r.type_confirmed ?? r.type_inferred;
        setActivities(ACTIVITY_DEFAULTS[typeKey] ?? []);
      }
      setNotes(r.furniture_notes ?? "");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load the room.");
      }
    }
  }, [pid, rid]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pid || !rid) return;
    setSubmitting(true);
    setError(null);
    try {
      await postFurniture(pid, rid, {
        furniture_notes: notes,
        activities,
      });
      router.push(`/studio/brief?${buildStudioQuery(pid, rid)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not save furniture notes.");
      }
      setSubmitting(false);
    }
  };

  if (!pid || !rid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/furniture" />
        <ErrorBanner message="Missing project or room id. Start from upload." />
      </div>
    );
  }

  if (room === null && !error) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/furniture" query={buildStudioQuery(pid, rid)} />
        <Spinner label="Loading the room…" />
      </div>
    );
  }

  const detected = room?.furniture_parsed ?? [];

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/furniture" query={buildStudioQuery(pid, rid)} />

      <div className="bg-stone-100 border border-stone-200 rounded-md px-4 py-3 flex items-center justify-between text-sm">
        <div>
          <span className="text-stone-500">Designing:</span>{" "}
          <span className="text-stone-900 font-medium">{room?.name}</span>
        </div>
        <Link
          href={`/studio/rooms?${buildStudioQuery(pid)}`}
          className="text-xs text-amber-700 hover:text-amber-800"
        >
          Back to rooms
        </Link>
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Furniture &amp; activities</h1>
        <p className="text-stone-600 text-sm">
          We&apos;ve detected furniture from your plan. Confirm what the room is for
          and add anything we missed.
        </p>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      <form onSubmit={onSubmit} className="space-y-8">
        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">
            Detected furniture
          </div>
          {detected.length > 0 ? (
            <ul className="border border-stone-200 rounded-md divide-y divide-stone-100 bg-white">
              {detected.map((f) => (
                <li
                  key={f.id}
                  className="px-3 py-2 text-sm text-stone-800 flex items-center justify-between"
                >
                  <span>{furnitureLabel(f)}</span>
                  <span className="text-xs text-stone-400">
                    {f.position.x.toFixed(1)}m, {f.position.y.toFixed(1)}m
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-stone-500 border border-dashed border-stone-200 rounded-md px-3 py-3">
              Nothing detected — drop a furniture plan file next time, or
              type below.
            </div>
          )}
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">
            Primary activities in this room
          </div>
          <OptionGroup
            options={ACTIVITY_OPTIONS}
            multi
            value={activities}
            onChange={(next) => setActivities(next)}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">
            Anything we missed?
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={4}
            placeholder='e.g. "8-seat dining table centered, sideboard along south wall" or "puja altar in NE corner"'
            className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
          />
        </section>

        <div className="flex justify-between pt-6 border-t border-stone-200">
          <Link
            href={`/studio/walls?${buildStudioQuery(pid, rid)}`}
            className="text-sm text-stone-500 hover:text-stone-700"
          >
            ← Back to walls
          </Link>
          {submitting ? (
            <Spinner label="Saving…" />
          ) : (
            <button
              type="submit"
              className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition"
            >
              Continue to brief →
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
