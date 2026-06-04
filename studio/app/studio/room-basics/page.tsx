"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type DoorMarker,
  type FurnitureMarker,
  RoomMiniMap,
  type WindowMarker,
} from "../components/RoomMiniMap";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, OptionGroup, Spinner } from "../components/UIPrimitives";
import { ApiError, getRoom, listRooms, postRoomBasics } from "@/lib/api/client";
import type {
  CeilingType,
  ConfirmedRoom,
  Direction,
  FinishTone,
  Furniture,
  Occupant,
  Point,
  RoomType,
} from "@/lib/api/types";
import { formatDim, parseDim } from "@/lib/format/dimensions";

/** Build a furniture marker label from a parser Furniture record. */
function markerLabel(f: Furniture): string {
  const type = f.type && f.type !== "unknown" ? f.type : "furniture";
  return f.raw_label && f.raw_label.length > 0
    ? `${type} — ${f.raw_label}`
    : type;
}

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
  { id: "flat", label: "Flat false ceiling (POP/gypsum)" },
  { id: "cove", label: "Cove — perimeter cove + raised central" },
  { id: "tray", label: "Tray — recessed central" },
  { id: "multi_level", label: "Multi-level (LVL ±0 / ±6 / etc.)" },
  { id: "pop_design", label: "POP design (decorative)" },
  { id: "wooden", label: "Wooden panels / slats" },
  { id: "fluted", label: "Fluted panels" },
  { id: "none", label: "Exposed RCC slab" },
  { id: "sloped", label: "Sloped / pitched" },
  { id: "mixed", label: "Mixed (combination)" },
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
  /** id → name map used to label door destinations in the mini-map tooltip. */
  const [roomNameById, setRoomNameById] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Local form state — initialised from the fetched ConfirmedRoom.
  const [typeConfirmed, setTypeConfirmed] = useState<RoomType | null>(null);
  // Dimension inputs accept feet OR meters (e.g. "12'-6\"", "3.8m", or bare
  // "3.8" assumed meters). String state captures whatever the user typed; on
  // blur it's reformatted to the canonical "X.Xm (XX'-Y\")" via parseDim +
  // formatDim. The parsed numeric value is what we POST.
  const [lengthInput, setLengthInput] = useState<string>("");
  const [widthInput, setWidthInput] = useState<string>("");
  const [ceilingHeightInput, setCeilingHeightInput] = useState<string>("");
  const [lengthErr, setLengthErr] = useState(false);
  const [widthErr, setWidthErr] = useState(false);
  const [ceilingHeightErr, setCeilingHeightErr] = useState(false);
  const [ceilingType, setCeilingType] = useState<CeilingType | null>(null);
  const [orientation, setOrientation] = useState<Direction | null>(null);
  const [occupants, setOccupants] = useState<Occupant[]>([]);
  const [floorFinish, setFloorFinish] = useState<FinishTone | null>(null);
  const [wallFinish, setWallFinish] = useState<FinishTone | null>(null);

  // Furniture markers for the inline mini-map. Derived from the loaded
  // ConfirmedRoom.furniture_parsed (populated by the Phase B furniture-merge
  // integration). Memoised so changes to other form state don't churn the
  // markers array reference.
  const furnitureMarkers: FurnitureMarker[] = useMemo(() => {
    const items = room?.furniture_parsed ?? [];
    return items.map((f) => ({
      position: f.position,
      label: markerLabel(f),
    }));
  }, [room?.furniture_parsed]);

  // Door + window markers — pulled from the parser's doors_parsed /
  // windows_parsed lists. Skip doors / windows that have no wall_index
  // (parser couldn't snap them to a specific polygon edge — rare).
  const doorMarkers: DoorMarker[] = useMemo(() => {
    const items = room?.doors_parsed ?? [];
    return items.flatMap((d) =>
      d.wall_index === null || d.wall_index === undefined ||
      d.along_wall === null || d.along_wall === undefined
        ? []
        : [{
            wallIndex: d.wall_index,
            alongWall: d.along_wall,
            widthM: d.width_m,
            destinationLabel: d.destination_room_id
              ? (roomNameById[d.destination_room_id] ?? undefined)
              : undefined,
          }],
    );
  }, [room?.doors_parsed, roomNameById]);

  const windowMarkers: WindowMarker[] = useMemo(() => {
    const items = room?.windows_parsed ?? [];
    return items.flatMap((w) =>
      w.wall_index === null || w.wall_index === undefined ||
      w.along_wall === null || w.along_wall === undefined
        ? []
        : [{
            wallIndex: w.wall_index,
            alongWall: w.along_wall,
            widthM: w.width_m,
            isDoorWindow: w.is_glazed_door,
          }],
    );
  }, [room?.windows_parsed]);

  // Default wall labels (A, B, C, …) — only used so RoomMiniMap renders
  // its wall letters; this screen doesn't drive wall selection.
  const wallLabels = useMemo<string[]>(() => {
    const n = room?.polygon_inferred.length ?? 0;
    return Array.from({ length: n }, (_, i) =>
      String.fromCharCode(65 + (i % 26)),
    );
  }, [room?.polygon_inferred.length]);

  const load = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id — start from /studio/upload.");
      return;
    }
    setError(null);
    try {
      const [r, rooms] = await Promise.all([
        getRoom(pid, rid),
        listRooms(pid),
      ]);
      setRoom(r);
      setRoomNameById(
        Object.fromEntries(rooms.rooms.map((rm) => [rm.id, rm.name])),
      );
      setTypeConfirmed(r.type_confirmed ?? r.type_inferred);
      // The /room endpoint returns ConfirmedRoom which doesn't carry RoomDims;
      // pre-fill from the polygon bounding box when the user hasn't typed
      // a value yet. We round to 2 decimals so the input doesn't look noisy.
      const dims = polygonDims(r.polygon_inferred);
      const initialLength =
        r.length_m !== null && r.length_m !== undefined
          ? r.length_m
          : dims.length > 0
            ? dims.length
            : null;
      const initialWidth =
        r.width_m !== null && r.width_m !== undefined
          ? r.width_m
          : dims.width > 0
            ? dims.width
            : null;
      const initialCeiling =
        r.ceiling_height_m !== null && r.ceiling_height_m !== undefined
          ? r.ceiling_height_m
          : DEFAULT_CEILING_HEIGHT_M;
      setLengthInput(initialLength !== null ? formatDim(initialLength) : "");
      setWidthInput(initialWidth !== null ? formatDim(initialWidth) : "");
      setCeilingHeightInput(formatDim(initialCeiling));
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

  /** Pull meters out of either a canonical "X.Xm (Y'-Z\")" display or any
   * parseDim-accepted format. Returns null for empty/unparseable input. */
  const inputToMeters = (input: string): number | null => {
    const trimmed = input.trim();
    if (trimmed.length === 0) return null;
    // Canonical display "4.2m (13'-9½\")" — take the meters part before " (".
    const canonical = trimmed.match(/^([+-]?\d+(?:\.\d+)?)\s*m\b/i);
    if (canonical) {
      const v = Number(canonical[1]);
      return Number.isFinite(v) ? v : null;
    }
    return parseDim(trimmed);
  };

  const onDimBlur = (
    raw: string,
    setInput: (s: string) => void,
    setErr: (b: boolean) => void,
  ) => {
    const trimmed = raw.trim();
    if (trimmed.length === 0) {
      setErr(false);
      return;
    }
    const meters = inputToMeters(trimmed);
    if (meters === null || meters <= 0) {
      setErr(true);
      return;
    }
    setErr(false);
    setInput(formatDim(meters));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pid || !rid) return;
    const lengthM = inputToMeters(lengthInput);
    const widthM = inputToMeters(widthInput);
    const ceilingHeightM = inputToMeters(ceilingHeightInput);
    // Reject submission if anything entered fails to parse.
    if (lengthInput.trim() !== "" && lengthM === null) {
      setLengthErr(true);
      return;
    }
    if (widthInput.trim() !== "" && widthM === null) {
      setWidthErr(true);
      return;
    }
    if (ceilingHeightInput.trim() !== "" && ceilingHeightM === null) {
      setCeilingHeightErr(true);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await postRoomBasics(pid, rid, {
        type_confirmed: typeConfirmed,
        length_m: lengthM,
        width_m: widthM,
        ceiling_height_m: ceilingHeightM,
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

      {room && room.polygon_inferred.length >= 3 && (
        <div className="flex items-start gap-4">
          <RoomMiniMap
            polygon={room.polygon_inferred}
            activeWallIndex={null}
            wallLabels={wallLabels}
            onSelectWall={() => {
              /* room-basics doesn't drive wall selection */
            }}
            furniture={furnitureMarkers}
            doors={doorMarkers}
            windows={windowMarkers}
          />
          <p className="text-xs text-stone-500 pt-2">
            Detected polygon and furniture from your plan. Confirm dimensions
            below if anything looks off.
          </p>
        </div>
      )}

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
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Dimensions</div>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <div className="text-xs text-stone-500 mb-1">Length</div>
              <input
                type="text"
                inputMode="text"
                value={lengthInput}
                onChange={(e) => {
                  setLengthInput(e.target.value);
                  if (lengthErr) setLengthErr(false);
                }}
                onBlur={(e) => onDimBlur(e.target.value, setLengthInput, setLengthErr)}
                className={`w-full bg-white border rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none ${
                  lengthErr ? "border-red-400" : "border-stone-200"
                }`}
              />
              {lengthErr && (
                <div className="text-[11px] text-red-700 mt-1">
                  Couldn&apos;t parse — try &quot;3.8m&quot; or &quot;12&apos;-6&quot;&quot;.
                </div>
              )}
            </label>
            <label className="block">
              <div className="text-xs text-stone-500 mb-1">Width</div>
              <input
                type="text"
                inputMode="text"
                value={widthInput}
                onChange={(e) => {
                  setWidthInput(e.target.value);
                  if (widthErr) setWidthErr(false);
                }}
                onBlur={(e) => onDimBlur(e.target.value, setWidthInput, setWidthErr)}
                className={`w-full bg-white border rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none ${
                  widthErr ? "border-red-400" : "border-stone-200"
                }`}
              />
              {widthErr && (
                <div className="text-[11px] text-red-700 mt-1">
                  Couldn&apos;t parse — try &quot;3.8m&quot; or &quot;12&apos;-6&quot;&quot;.
                </div>
              )}
            </label>
            <label className="block">
              <div className="text-xs text-stone-500 mb-1">Ceiling height</div>
              <input
                type="text"
                inputMode="text"
                value={ceilingHeightInput}
                onChange={(e) => {
                  setCeilingHeightInput(e.target.value);
                  if (ceilingHeightErr) setCeilingHeightErr(false);
                }}
                onBlur={(e) =>
                  onDimBlur(e.target.value, setCeilingHeightInput, setCeilingHeightErr)
                }
                className={`w-full bg-white border rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none ${
                  ceilingHeightErr ? "border-red-400" : "border-stone-200"
                }`}
              />
              {ceilingHeightErr && (
                <div className="text-[11px] text-red-700 mt-1">
                  Couldn&apos;t parse — try &quot;2.8m&quot; or &quot;9&apos;-0&quot;&quot;.
                </div>
              )}
            </label>
          </div>
          <p className="text-xs text-stone-500">
            Enter in feet or meters — e.g. <span className="text-stone-700">3.8m</span>{" "}
            or <span className="text-stone-700">12&apos;-6&quot;</span>. Values are
            stored in meters and reformatted on blur. Ceiling height defaults to{" "}
            {formatDim(DEFAULT_CEILING_HEIGHT_M)}.
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
