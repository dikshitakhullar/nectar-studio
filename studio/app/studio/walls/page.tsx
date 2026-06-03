"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import { ApiError, getWalls, postWall } from "@/lib/api/client";
import type { WallConfirmation } from "@/lib/api/types";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

export default function WallsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [walls, setWalls] = useState<WallConfirmation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id.");
      return;
    }
    setError(null);
    try {
      const result = await getWalls(pid, rid);
      setWalls(result.walls);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load walls.");
      }
    }
  }, [pid, rid]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleConfirm = (index: number) => {
    setWalls((prev) =>
      prev
        ? prev.map((w) =>
            w.index === index ? { ...w, confirm: !(w.confirm ?? false) } : w,
          )
        : prev,
    );
  };

  const updateNotes = (index: number, notes: string) => {
    setWalls((prev) =>
      prev ? prev.map((w) => (w.index === index ? { ...w, notes } : w)) : prev,
    );
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pid || !rid || !walls) return;
    setSubmitting(true);
    setError(null);
    try {
      // Post each wall sequentially so any 400 surfaces clearly to the user.
      for (const wall of walls) {
        await postWall(pid, rid, wall.index, {
          index: wall.index,
          confirm: wall.confirm ?? true,
          doors_confirmed: wall.doors_confirmed ?? [],
          windows_confirmed: wall.windows_confirmed ?? [],
          notes: wall.notes ?? "",
        });
      }
      router.push(`/studio/furniture?${buildStudioQuery(pid, rid)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not save walls.");
      }
      setSubmitting(false);
    }
  };

  if (!pid || !rid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/walls" />
        <ErrorBanner message="Missing project or room id. Start from upload." />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/walls" query={buildStudioQuery(pid, rid)} />

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Walls</h1>
        <p className="text-stone-600 text-sm">
          One row per wall, derived from the parsed polygon. Confirm the wall
          exists (it should — checked by default), and add a short note if
          there&apos;s something the parser missed.
        </p>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}
      {!error && walls === null && <Spinner label="Loading walls…" />}

      {walls !== null && walls.length === 0 && (
        <div className="bg-stone-100 border border-stone-200 rounded-md p-4 text-sm text-stone-700">
          The parser didn&apos;t return any wall edges — this is unusual. You
          can still continue.
        </div>
      )}

      {walls !== null && walls.length > 0 && (
        <form onSubmit={onSubmit} className="space-y-4">
          <ul className="space-y-2">
            {walls.map((wall) => (
              <li
                key={wall.index}
                className="bg-white border border-stone-200 rounded-md p-3 space-y-2"
              >
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={wall.confirm ?? false}
                    onChange={() => toggleConfirm(wall.index)}
                    className="rounded border-stone-300 text-amber-700 focus:ring-amber-700"
                  />
                  <div className="flex-1">
                    <div className="text-sm font-medium text-stone-900">
                      Wall #{wall.index}
                    </div>
                    <div className="text-xs text-stone-500">
                      {(wall.doors_confirmed?.length ?? 0)} door
                      {(wall.doors_confirmed?.length ?? 0) === 1 ? "" : "s"} ·{" "}
                      {(wall.windows_confirmed?.length ?? 0)} window
                      {(wall.windows_confirmed?.length ?? 0) === 1 ? "" : "s"}
                    </div>
                  </div>
                </label>
                <input
                  type="text"
                  value={wall.notes ?? ""}
                  onChange={(e) => updateNotes(wall.index, e.target.value)}
                  placeholder="Notes (optional)"
                  className="w-full bg-stone-50 border border-stone-200 rounded-md px-3 py-1.5 text-xs text-stone-900 focus:border-stone-400 outline-none"
                />
              </li>
            ))}
          </ul>

          <div className="flex justify-between pt-6 border-t border-stone-200">
            <Link
              href={`/studio/room-basics?${buildStudioQuery(pid, rid)}`}
              className="text-sm text-stone-500 hover:text-stone-700"
            >
              ← Back to room basics
            </Link>
            {submitting ? (
              <Spinner label="Saving walls…" />
            ) : (
              <button
                type="submit"
                className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition"
              >
                Continue to furniture →
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
