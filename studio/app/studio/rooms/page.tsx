"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import { ApiError, listRooms } from "@/lib/api/client";
import type { RoomSummary } from "@/lib/api/types";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

const ROOM_TYPE_LABELS: Record<string, string> = {
  living: "Living",
  dining: "Dining",
  bedroom: "Bedroom",
  kitchen: "Kitchen",
  bathroom: "Bathroom",
  study: "Study",
  hallway: "Hallway",
  staircase: "Staircase",
  foyer: "Foyer",
  outdoor: "Outdoor",
  unknown: "Unknown",
};

const STATUS_LABELS: Record<string, string> = {
  new: "Not started",
  basics_confirmed: "Basics confirmed",
  walls_confirmed: "Walls confirmed",
  furniture_confirmed: "Furniture confirmed",
  brief_confirmed: "Brief confirmed",
  plan_ready: "Plan ready",
};

export default function RoomsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid } = readStudioIds(searchParams);
  const [rooms, setRooms] = useState<RoomSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!pid) {
      setError("Missing project id — start from /studio/upload.");
      return;
    }
    setError(null);
    try {
      const result = await listRooms(pid);
      setRooms(result.rooms);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load rooms.");
      }
    }
  }, [pid]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!pid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/rooms" />
        <ErrorBanner message="No project id in the URL. Start from upload." />
        <Link href="/studio/upload" className="text-sm text-amber-700 hover:text-amber-800">
          ← Back to upload
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/rooms" query={buildStudioQuery(pid)} />

      <div className="space-y-2">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Rooms</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Pick a room to design</h1>
        <p className="text-stone-600 text-sm">
          We parsed your ceiling DWG and found these rooms. Pick one to walk
          through the clarification flow.
        </p>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}
      {!error && rooms === null && <Spinner label="Loading rooms…" />}

      {rooms !== null && rooms.length === 0 && !error && (
        <div className="bg-stone-100 border border-stone-200 rounded-md p-6 text-sm text-stone-700">
          We couldn&apos;t find any first-class rooms in that file. Try a
          different DWG/DXF with labelled living/dining/bedroom areas.
        </div>
      )}

      {rooms !== null && rooms.length > 0 && (
        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">
            Rooms ({rooms.length})
          </div>
          <div className="space-y-2">
            {rooms.map((room) => {
              const dims = `${room.dims.length_m.toFixed(2)} × ${room.dims.width_m.toFixed(2)} m`;
              const typeLabel = ROOM_TYPE_LABELS[room.type] ?? room.type;
              const statusLabel = STATUS_LABELS[room.status ?? "new"] ?? room.status ?? "Not started";
              return (
                <button
                  key={room.id}
                  type="button"
                  onClick={() => {
                    router.push(
                      `/studio/room-basics?${buildStudioQuery(pid, room.id)}`,
                    );
                  }}
                  className="w-full text-left bg-white border border-stone-200 rounded-md p-4 hover:border-amber-700 transition"
                >
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex-1">
                      <div className="text-sm font-medium text-stone-900">
                        {room.name}{" "}
                        <span className="text-xs uppercase tracking-wider text-amber-700/90 ml-1">
                          {typeLabel}
                        </span>
                      </div>
                      <div className="text-xs text-stone-500 mt-1">
                        {dims} · {room.doors.length} door
                        {room.doors.length === 1 ? "" : "s"} · {room.windows.length} window
                        {room.windows.length === 1 ? "" : "s"} · {statusLabel}
                      </div>
                    </div>
                    <div className="text-stone-400">→</div>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      )}

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/upload" className="text-sm text-stone-500 hover:text-stone-700">
          ← Back to upload
        </Link>
      </div>
    </div>
  );
}
