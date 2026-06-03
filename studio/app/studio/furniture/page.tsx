"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import { ApiError, postFurniture } from "@/lib/api/client";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

export default function FurniturePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pid || !rid) return;
    setSubmitting(true);
    setError(null);
    try {
      await postFurniture(pid, rid, { furniture_notes: notes });
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

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/furniture" query={buildStudioQuery(pid, rid)} />

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Furniture layout</h1>
        <p className="text-stone-600 text-sm">
          Briefly describe what the room is for and where the big pieces sit.
          The lighting engine uses this to place pendants, task lights, and
          accent fixtures.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      <form onSubmit={onSubmit} className="space-y-6">
        <label className="block space-y-2">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Furniture + usage notes</div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={5}
            placeholder='e.g. "family meals" or "8-seat dining table centered, sideboard along south wall"'
            className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
          />
        </label>

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
