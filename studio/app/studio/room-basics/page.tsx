"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, OptionGroup, Spinner } from "../components/UIPrimitives";
import { ApiError, getRoom, postRoomBasics } from "@/lib/api/client";
import type {
  CeilingType,
  ConfirmedRoom,
  Direction,
  FinishTone,
  Occupant,
  Point,
  RoomType,
} from "@/lib/api/types";

/** Bounding-box dims of a polygon — used as a default for length/width if the
 * user hasn't typed values yet. The /room endpoint doesn't carry dims directly. */
function polygonDims(polygon: Point[]): { length: number; width: number } {
  if (polygon.length === 0) return { length: 0, width: 0 };
  let minX = polygon[0].x;
  let maxX = polygon[0].x;
  let minY = polygon[0].y;
  let maxY = polygon[0].y;
  for (const p of polygon) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  // Convention: length is the longer side, width the shorter — matches RoomDims.
  const a = maxX - minX;
  const b = maxY - minY;
  return { length: Math.max(a, b), width: Math.min(a, b) };
}
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

const DEFAULT_CEILING_HEIGHT_M = 2.8;

const ROOM_TYPE_OPTIONS: { id: RoomType; label: string }[] = [
  { id: "living", label: "Living / TV room" },
  { id: "dining", label: "Dining room" },
  { id: "bedroom", label: "Bedroom" },
  { id: "kitchen", label: "Kitchen" },
  { id: "study", label: "Study / WFH" },
  { id: "bathroom", label: "Bathroom" },
];

const CEILING_TYPE_OPTIONS: { id: CeilingType; label: string }[] = [
  { id: "flat", label: "Flat (no false ceiling)" },
  { id: "none", label: "Exposed slab" },
  { id: "sloped", label: "Sloped" },
  { id: "mixed", label: "Mixed" },
];

const DIRECTION_OPTIONS: { id: Direction; label: string; description?: string }[] = [
  { id: "N", label: "North" },
  { id: "S", label: "South" },
  { id: "E", label: "East", description: "Morning sun" },
  { id: "W", label: "West", description: "Evening sun" },
];

const OCCUPANT_OPTIONS: { id: Occupant; label: string; description?: string }[] = [
  { id: "kids", label: "Kids" },
  { id: "young_adult", label: "Teen / young adult" },
  { id: "adult", label: "Adult (30s–50s)" },
  { id: "elderly", label: "Elderly", description: "Higher lux + glare control" },
];

const FINISH_OPTIONS: { id: FinishTone; label: string }[] = [
  { id: "light", label: "Light" },
  { id: "mid", label: "Mid" },
  { id: "dark", label: "Dark" },
];

export default function RoomBasicsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [room, setRoom] = useState<ConfirmedRoom | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Local form state — initialised from the fetched ConfirmedRoom.
  const [typeConfirmed, setTypeConfirmed] = useState<RoomType | null>(null);
  const [lengthM, setLengthM] = useState<string>("");
  const [widthM, setWidthM] = useState<string>("");
  const [ceilingHeightM, setCeilingHeightM] = useState<string>("");
  const [ceilingType, setCeilingType] = useState<CeilingType | null>(null);
  const [orientation, setOrientation] = useState<Direction | null>(null);
  const [occupants, setOccupants] = useState<Occupant[]>([]);
  const [floorFinish, setFloorFinish] = useState<FinishTone | null>(null);
  const [wallFinish, setWallFinish] = useState<FinishTone | null>(null);

  const load = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id — start from /studio/upload.");
      return;
    }
    setError(null);
    try {
      const r = await getRoom(pid, rid);
      setRoom(r);
      setTypeConfirmed(r.type_confirmed ?? r.type_inferred);
      // The /room endpoint returns ConfirmedRoom which doesn't carry RoomDims;
      // pre-fill from the polygon bounding box when the user hasn't typed
      // a value yet. We round to 2 decimals so the input doesn't look noisy.
      const dims = polygonDims(r.polygon_inferred);
      setLengthM(
        r.length_m !== null && r.length_m !== undefined
          ? String(r.length_m)
          : dims.length > 0 ? dims.length.toFixed(2) : "",
      );
      setWidthM(
        r.width_m !== null && r.width_m !== undefined
          ? String(r.width_m)
          : dims.width > 0 ? dims.width.toFixed(2) : "",
      );
      setCeilingHeightM(
        r.ceiling_height_m !== null && r.ceiling_height_m !== undefined
          ? String(r.ceiling_height_m)
          : String(DEFAULT_CEILING_HEIGHT_M),
      );
      setCeilingType(r.ceiling_type ?? "flat");
      setOrientation(r.main_window_orientation ?? null);
      setOccupants(r.occupants ?? []);
      setFloorFinish(r.floor_finish ?? null);
      setWallFinish(r.wall_finish ?? null);
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
      await postRoomBasics(pid, rid, {
        type_confirmed: typeConfirmed,
        length_m: lengthM ? Number(lengthM) : null,
        width_m: widthM ? Number(widthM) : null,
        ceiling_height_m: ceilingHeightM ? Number(ceilingHeightM) : null,
        ceiling_type: ceilingType,
        main_window_orientation: orientation,
        occupants: occupants.length > 0 ? occupants : null,
        floor_finish: floorFinish,
        wall_finish: wallFinish,
      });
      router.push(`/studio/walls?${buildStudioQuery(pid, rid)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Could not save room basics.");
      }
      setSubmitting(false);
    }
  };

  if (!pid || !rid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/room-basics" />
        <ErrorBanner message="Missing project or room id. Start from upload." />
        <Link href="/studio/upload" className="text-sm text-amber-700 hover:text-amber-800">
          ← Back to upload
        </Link>
      </div>
    );
  }

  if (room === null && !error) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/room-basics" query={buildStudioQuery(pid, rid)} />
        <Spinner label="Loading the room…" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/room-basics" query={buildStudioQuery(pid, rid)} />

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
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Room basics</h1>
        <p className="text-stone-600 text-sm">
          Confirm room type, dimensions, ceiling, orientation, and finishes.
        </p>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}

      <form onSubmit={onSubmit} className="space-y-8">
        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Room type</div>
          <OptionGroup
            options={ROOM_TYPE_OPTIONS}
            value={typeConfirmed ? [typeConfirmed] : []}
            onChange={(next) => setTypeConfirmed((next[0] as RoomType) ?? null)}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Dimensions (m)</div>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <div className="text-xs text-stone-500 mb-1">Length</div>
              <input
                type="number"
                step="0.01"
                value={lengthM}
                onChange={(e) => setLengthM(e.target.value)}
                className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none"
              />
            </label>
            <label className="block">
              <div className="text-xs text-stone-500 mb-1">Width</div>
              <input
                type="number"
                step="0.01"
                value={widthM}
                onChange={(e) => setWidthM(e.target.value)}
                className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none"
              />
            </label>
            <label className="block">
              <div className="text-xs text-stone-500 mb-1">Ceiling height</div>
              <input
                type="number"
                step="0.01"
                value={ceilingHeightM}
                onChange={(e) => setCeilingHeightM(e.target.value)}
                className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none"
              />
            </label>
          </div>
          <p className="text-xs text-stone-500">
            Length and width come from the parsed polygon. Ceiling height defaults to {DEFAULT_CEILING_HEIGHT_M} m — edit if your project differs.
          </p>
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Ceiling type</div>
          <OptionGroup
            options={CEILING_TYPE_OPTIONS}
            value={ceilingType ? [ceilingType] : []}
            onChange={(next) => setCeilingType((next[0] as CeilingType) ?? null)}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Main window faces</div>
          <OptionGroup
            options={DIRECTION_OPTIONS}
            value={orientation ? [orientation] : []}
            onChange={(next) => setOrientation((next[0] as Direction) ?? null)}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Who uses this room?</div>
          <OptionGroup
            options={OCCUPANT_OPTIONS}
            multi
            value={occupants}
            onChange={(next) => setOccupants(next as Occupant[])}
          />
        </section>

        <section className="space-y-3">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Floor + wall finish</div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-stone-500 mb-2">Floor</div>
              <OptionGroup
                options={FINISH_OPTIONS}
                value={floorFinish ? [floorFinish] : []}
                onChange={(next) => setFloorFinish((next[0] as FinishTone) ?? null)}
              />
            </div>
            <div>
              <div className="text-xs text-stone-500 mb-2">Walls</div>
              <OptionGroup
                options={FINISH_OPTIONS}
                value={wallFinish ? [wallFinish] : []}
                onChange={(next) => setWallFinish((next[0] as FinishTone) ?? null)}
              />
            </div>
          </div>
        </section>

        <div className="flex justify-between pt-6 border-t border-stone-200">
          <Link
            href={`/studio/rooms?${buildStudioQuery(pid)}`}
            className="text-sm text-stone-500 hover:text-stone-700"
          >
            ← Back
          </Link>
          {submitting ? (
            <Spinner label="Saving…" />
          ) : (
            <button
              type="submit"
              className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition"
            >
              Continue to walls →
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
