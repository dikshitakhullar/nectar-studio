"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { StepNav } from "../components/StepNav";
import {
  type DoorMarker,
  RoomMiniMap,
  type WindowMarker,
} from "../components/RoomMiniMap";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import { ApiError, getRoom, getWalls, listRooms, postWall } from "@/lib/api/client";
import type {
  Door,
  Point,
  RoomSummary,
  WallConfirmation,
  Window as ApiWindow,
} from "@/lib/api/types";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";
import { formatDim } from "@/lib/format/dimensions";

// ---------------------------------------------------------------------------
// Per-wall structured state — packed into WallConfirmation.notes as JSON for
// v1.0.1. Promoted to first-class API fields in v1.1.
// ---------------------------------------------------------------------------

type DoorType = "regular" | "sliding" | "double" | "pocket" | "bifold";
const DOOR_TYPES: { value: DoorType; label: string }[] = [
  { value: "regular", label: "Regular swing" },
  { value: "sliding", label: "Sliding" },
  { value: "double", label: "Double" },
  { value: "pocket", label: "Pocket" },
  { value: "bifold", label: "Bifold" },
];

interface WallExtras {
  has_door: boolean;
  door_type?: DoorType;
  leads_to?: string;          // room id of adjacent room
  has_window: boolean;
  window_width_m?: number;
  window_height_m?: number;
  window_sill_height_m?: number;
}

function packNotes(extras: WallExtras, userNotes: string): string {
  return JSON.stringify({ extras, notes: userNotes });
}

function unpackNotes(
  notes: string | undefined,
): { extras: WallExtras; notes: string; pristine: boolean } {
  if (!notes) return { extras: emptyExtras(), notes: "", pristine: true };
  try {
    const parsed = JSON.parse(notes) as { extras?: WallExtras; notes?: string };
    if (parsed && typeof parsed === "object" && parsed.extras) {
      return {
        extras: { ...emptyExtras(), ...parsed.extras },
        notes: parsed.notes ?? "",
        pristine: false,
      };
    }
  } catch {
    // Legacy notes (pre-v1.0.1) — plain string; treat as the user-notes field.
  }
  return { extras: emptyExtras(), notes, pristine: false };
}

function emptyExtras(): WallExtras {
  return { has_door: false, has_window: false };
}

/** Map a Door's `swing` value to a `DoorType` for the dropdown. The studio's
 * door-type vocabulary is richer than the parser's (which only knows in/out/
 * sliding/unknown), so non-sliding swings collapse to "regular". */
function doorTypeFromSwing(swing: Door["swing"] | undefined): DoorType {
  return swing === "sliding" ? "sliding" : "regular";
}

interface PrefillArgs {
  wallIndex: number;
  extras: WallExtras;
  /** True when the wall has never been saved (notes string was empty). Only
   * pristine walls get pre-filled from parsed openings — once the designer
   * has saved this wall, their choices are sticky. */
  pristine: boolean;
  parsedDoors: Door[];
  parsedWindows: ApiWindow[];
  otherRoomIds: Set<string>;
}

/**
 * Pre-fill `extras` from parsed doors / windows on this wall.
 *
 * Only runs for pristine walls (those that have never been saved). Once the
 * designer has saved the wall — even with `has_door = false` — we treat their
 * decision as authoritative and don't second-guess it.
 *
 * Multiple parsed doors on one wall (rare: wardrobe + entry on the same long
 * wall) collapse to the first detected destination — the designer can edit.
 */
function prefillWallExtras({
  wallIndex,
  extras,
  pristine,
  parsedDoors,
  parsedWindows,
  otherRoomIds,
}: PrefillArgs): WallExtras {
  if (!pristine) return extras;
  const next: WallExtras = { ...extras };
  const doorOnWall = parsedDoors.find((d) => d.wall_index === wallIndex);
  if (doorOnWall) {
    next.has_door = true;
    next.door_type = doorTypeFromSwing(doorOnWall.swing);
    // Only adopt the parser's destination if the target room is still in the
    // dropdown list — protects against stale ids after a re-parse.
    if (
      doorOnWall.destination_room_id &&
      otherRoomIds.has(doorOnWall.destination_room_id)
    ) {
      next.leads_to = doorOnWall.destination_room_id;
    }
  }
  const winOnWall = parsedWindows.find((w) => w.wall_index === wallIndex);
  if (winOnWall) {
    next.has_window = true;
    next.window_width_m = winOnWall.width_m;
    next.window_height_m = winOnWall.height_m;
    next.window_sill_height_m = winOnWall.sill_height_m;
  }
  return next;
}

// ---------------------------------------------------------------------------
// Polygon helpers — wall direction (N/S/E/W) + length from polygon edge.
// ---------------------------------------------------------------------------

function polygonCentroid(polygon: Point[]): Point {
  const n = polygon.length;
  return {
    x: polygon.reduce((s, p) => s + p.x, 0) / n,
    y: polygon.reduce((s, p) => s + p.y, 0) / n,
  };
}

function wallLength(polygon: Point[], index: number): number {
  const a = polygon[index];
  const b = polygon[(index + 1) % polygon.length];
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** Direction the wall faces (outward normal). Local frame: y is north. */
function wallDirection(polygon: Point[], index: number): string {
  const a = polygon[index];
  const b = polygon[(index + 1) % polygon.length];
  const centroid = polygonCentroid(polygon);
  const midX = (a.x + b.x) / 2;
  const midY = (a.y + b.y) / 2;
  // Outward vector from polygon centroid to edge midpoint.
  const dx = midX - centroid.x;
  const dy = midY - centroid.y;
  const angle = Math.atan2(dy, dx) * 180 / Math.PI;
  if (angle >= -22.5 && angle < 22.5) return "East";
  if (angle >= 22.5 && angle < 67.5) return "Northeast";
  if (angle >= 67.5 && angle < 112.5) return "North";
  if (angle >= 112.5 && angle < 157.5) return "Northwest";
  if (angle >= 157.5 || angle < -157.5) return "West";
  if (angle >= -157.5 && angle < -112.5) return "Southwest";
  if (angle >= -112.5 && angle < -67.5) return "South";
  return "Southeast";
}

function wallLetter(index: number): string {
  // A, B, C, ..., Z, AA, AB, ...
  if (index < 26) return String.fromCharCode(65 + index);
  const first = Math.floor(index / 26) - 1;
  const second = index % 26;
  return String.fromCharCode(65 + first) + String.fromCharCode(65 + second);
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface WallState extends WallConfirmation {
  extras: WallExtras;
  userNotes: string;
}

const SAVE_DEBOUNCE_MS = 500;

export default function WallsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [polygon, setPolygon] = useState<Point[] | null>(null);
  const [walls, setWalls] = useState<WallState[] | null>(null);
  const [otherRooms, setOtherRooms] = useState<RoomSummary[]>([]);
  /** Parsed doors / windows from the /room endpoint — used to render the
   * door arcs + window symbols on the mini-map AND to pre-fill per-wall
   * defaults. Kept separate from the WallConfirmation list because the
   * latter is the user-editable state, while this is the parser snapshot. */
  const [parsedDoors, setParsedDoors] = useState<Door[]>([]);
  const [parsedWindows, setParsedWindows] = useState<ApiWindow[]>([]);
  const [activeWallIndex, setActiveWallIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const wallRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const load = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id.");
      return;
    }
    setError(null);
    try {
      const [room, wallsResult, rooms] = await Promise.all([
        getRoom(pid, rid),
        getWalls(pid, rid),
        listRooms(pid),
      ]);
      setPolygon(room.polygon_inferred);
      const parsedDoorsList = room.doors_parsed ?? [];
      const parsedWindowsList = room.windows_parsed ?? [];
      setParsedDoors(parsedDoorsList);
      setParsedWindows(parsedWindowsList);
      const otherRoomList = rooms.rooms.filter((r) => r.id !== rid);
      const otherIdSet = new Set(otherRoomList.map((r) => r.id));
      const hydrated: WallState[] = wallsResult.walls.map((w) => {
        const { extras, notes, pristine } = unpackNotes(w.notes);
        // Phase C: pre-fill door/window defaults from parsed openings on
        // pristine walls (those the designer has never saved). Once the
        // designer has saved a wall, their choices are sticky and we don't
        // second-guess them — even `has_door = false` stays false.
        const prefilled = prefillWallExtras({
          wallIndex: w.index,
          extras,
          pristine,
          parsedDoors: parsedDoorsList,
          parsedWindows: parsedWindowsList,
          otherRoomIds: otherIdSet,
        });
        return { ...w, extras: prefilled, userNotes: notes };
      });
      setWalls(hydrated);
      setOtherRooms(otherRoomList);
      if (hydrated.length > 0 && activeWallIndex === null) {
        setActiveWallIndex(hydrated[0].index);
      }
    } catch (err) {
      setError(formatErr(err, "Failed to load walls."));
    }
  }, [pid, rid, activeWallIndex]);

  useEffect(() => { void load(); }, [load]);

  // Debounced auto-save: when a wall's local state changes, POST after 500ms.
  const saveTimers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());
  const scheduleSave = useCallback((wall: WallState) => {
    if (!pid || !rid) return;
    const existing = saveTimers.current.get(wall.index);
    if (existing) clearTimeout(existing);
    const timer = setTimeout(() => {
      void postWall(pid, rid, wall.index, {
        index: wall.index,
        confirm: wall.confirm ?? true,
        doors_confirmed: wall.doors_confirmed ?? [],
        windows_confirmed: wall.windows_confirmed ?? [],
        notes: packNotes(wall.extras, wall.userNotes),
      }).catch((err) => setError(formatErr(err, "Couldn't save wall.")));
    }, SAVE_DEBOUNCE_MS);
    saveTimers.current.set(wall.index, timer);
  }, [pid, rid]);

  const updateWall = useCallback(
    (index: number, mutate: (w: WallState) => WallState) => {
      setWalls((prev) => {
        if (!prev) return prev;
        const next = prev.map((w) => (w.index === index ? mutate(w) : w));
        const changed = next.find((w) => w.index === index);
        if (changed) scheduleSave(changed);
        return next;
      });
    },
    [scheduleSave],
  );

  const onSelectWall = useCallback((index: number) => {
    setActiveWallIndex(index);
    const el = wallRefs.current.get(index);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const onContinue = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pid || !rid || !walls) return;
    setSubmitting(true);
    setError(null);
    // Flush any pending debounced saves before navigating.
    for (const timer of saveTimers.current.values()) clearTimeout(timer);
    try {
      for (const wall of walls) {
        await postWall(pid, rid, wall.index, {
          index: wall.index,
          confirm: wall.confirm ?? true,
          doors_confirmed: wall.doors_confirmed ?? [],
          windows_confirmed: wall.windows_confirmed ?? [],
          notes: packNotes(wall.extras, wall.userNotes),
        });
      }
      router.push(`/studio/furniture?${buildStudioQuery(pid, rid)}`);
    } catch (err) {
      setError(formatErr(err, "Couldn't save walls."));
      setSubmitting(false);
    }
  };

  const wallLabels = useMemo(
    () => walls?.map((w) => wallLetter(w.index)) ?? [],
    [walls],
  );

  // Lookup so the door tooltip can show "Door (leads to Kitchen)" rather than
  // the raw room id. Built from `otherRooms` because every destination is by
  // definition not the current room.
  const otherRoomNameById = useMemo(
    () => Object.fromEntries(otherRooms.map((r) => [r.id, r.name])),
    [otherRooms],
  );

  const doorMarkers: DoorMarker[] = useMemo(() => {
    return parsedDoors.flatMap((d) =>
      d.wall_index === null || d.wall_index === undefined ||
      d.along_wall === null || d.along_wall === undefined
        ? []
        : [{
            wallIndex: d.wall_index,
            alongWall: d.along_wall,
            widthM: d.width_m,
            destinationLabel: d.destination_room_id
              ? (otherRoomNameById[d.destination_room_id] ?? undefined)
              : undefined,
          }],
    );
  }, [parsedDoors, otherRoomNameById]);

  const windowMarkers: WindowMarker[] = useMemo(() => {
    return parsedWindows.flatMap((w) =>
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
  }, [parsedWindows]);

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
          Confirm what&apos;s on each wall, or correct what the parser detected.
          Tap a wall on the map to jump to its card.
        </p>
      </div>

      {error && <ErrorBanner message={error} onRetry={load} />}
      {!error && walls === null && <Spinner label="Loading walls…" />}

      {walls !== null && walls.length === 0 && (
        <div className="bg-stone-100 border border-stone-200 rounded-md p-4 text-sm text-stone-700">
          The parser didn&apos;t return any wall edges — unusual. You can still
          continue.
        </div>
      )}

      {walls !== null && walls.length > 0 && polygon !== null && (
        <form onSubmit={onContinue} className="grid gap-6 md:grid-cols-[260px_1fr]">
          {/* Left rail — sticky mini-map */}
          <aside className="space-y-3 md:sticky md:top-6 md:self-start">
            <RoomMiniMap
              polygon={polygon}
              activeWallIndex={activeWallIndex}
              wallLabels={wallLabels}
              onSelectWall={onSelectWall}
              doors={doorMarkers}
              windows={windowMarkers}
            />
            <p className="text-xs text-stone-500 text-center">
              Tap a wall on the map to edit
            </p>
          </aside>

          {/* Right column — wall cards */}
          <div className="space-y-3">
            {walls.map((wall) => (
              <WallCard
                key={wall.index}
                wall={wall}
                polygon={polygon}
                otherRooms={otherRooms}
                isActive={activeWallIndex === wall.index}
                onFocus={() => setActiveWallIndex(wall.index)}
                onUpdate={(mutate) => updateWall(wall.index, mutate)}
                cardRef={(el) => {
                  if (el) wallRefs.current.set(wall.index, el);
                  else wallRefs.current.delete(wall.index);
                }}
              />
            ))}

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
          </div>
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// WallCard — per-wall structured inputs.
// ---------------------------------------------------------------------------

interface WallCardProps {
  wall: WallState;
  polygon: Point[];
  otherRooms: RoomSummary[];
  isActive: boolean;
  onFocus: () => void;
  onUpdate: (mutate: (w: WallState) => WallState) => void;
  cardRef: (el: HTMLDivElement | null) => void;
}

function WallCard({
  wall, polygon, otherRooms, isActive, onFocus, onUpdate, cardRef,
}: WallCardProps) {
  const direction = wallDirection(polygon, wall.index);
  const lengthM = wallLength(polygon, wall.index);
  const detectedDoors = wall.doors_confirmed?.length ?? 0;
  const detectedWindows = wall.windows_confirmed?.length ?? 0;
  const isSolid = !wall.extras.has_door && !wall.extras.has_window;

  return (
    <div
      ref={cardRef}
      onFocus={onFocus}
      onClick={onFocus}
      className={`bg-white border rounded-md p-4 space-y-3 transition ${
        isActive ? "border-amber-700 shadow-sm" : "border-stone-200"
      }`}
    >
      {/* Header */}
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="text-sm font-medium text-stone-900">
            Wall {wallLetter(wall.index)} — {direction}
          </div>
          <div className="text-xs text-stone-500">
            {formatDim(lengthM)}
            {(detectedDoors > 0 || detectedWindows > 0) && (
              <> · detected {detectedDoors} door{detectedDoors === 1 ? "" : "s"}, {detectedWindows} window{detectedWindows === 1 ? "" : "s"}</>
            )}
          </div>
        </div>
        {isSolid && (
          <span className="text-xs text-stone-400 italic">solid wall</span>
        )}
      </div>

      {/* Door section */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={wall.extras.has_door}
          onChange={(e) =>
            onUpdate((w) => ({
              ...w,
              extras: { ...w.extras, has_door: e.target.checked },
            }))
          }
          className="rounded border-stone-300 text-amber-700 focus:ring-amber-700"
        />
        <span className="text-sm text-stone-800">Has a door</span>
      </label>
      {wall.extras.has_door && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pl-6">
          <label className="block text-xs">
            <span className="block text-stone-500 mb-1">Type</span>
            <select
              value={wall.extras.door_type ?? "regular"}
              onChange={(e) =>
                onUpdate((w) => ({
                  ...w,
                  extras: { ...w.extras, door_type: e.target.value as DoorType },
                }))
              }
              className="w-full bg-stone-50 border border-stone-200 rounded-md px-3 py-1.5 text-stone-900 focus:border-stone-400 outline-none"
            >
              {DOOR_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>
          <label className="block text-xs">
            <span className="block text-stone-500 mb-1">Leads to</span>
            <select
              value={wall.extras.leads_to ?? ""}
              onChange={(e) =>
                onUpdate((w) => ({
                  ...w,
                  extras: { ...w.extras, leads_to: e.target.value || undefined },
                }))
              }
              className="w-full bg-stone-50 border border-stone-200 rounded-md px-3 py-1.5 text-stone-900 focus:border-stone-400 outline-none"
              disabled={otherRooms.length === 0}
            >
              <option value="">
                {otherRooms.length === 0 ? "(no other rooms)" : "Select…"}
              </option>
              {otherRooms.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </label>
        </div>
      )}

      {/* Window section */}
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={wall.extras.has_window}
          onChange={(e) =>
            onUpdate((w) => ({
              ...w,
              extras: {
                ...w.extras,
                has_window: e.target.checked,
                window_width_m: e.target.checked ? (w.extras.window_width_m ?? 1.2) : undefined,
                window_height_m: e.target.checked ? (w.extras.window_height_m ?? 1.2) : undefined,
                window_sill_height_m: e.target.checked ? (w.extras.window_sill_height_m ?? 0.9) : undefined,
              },
            }))
          }
          className="rounded border-stone-300 text-amber-700 focus:ring-amber-700"
        />
        <span className="text-sm text-stone-800">Has a window</span>
      </label>
      {wall.extras.has_window && (
        <div className="grid grid-cols-3 gap-2 pl-6">
          <DimInput
            label="Width"
            value={wall.extras.window_width_m ?? 1.2}
            onChange={(v) =>
              onUpdate((w) => ({
                ...w,
                extras: { ...w.extras, window_width_m: v },
              }))
            }
          />
          <DimInput
            label="Height"
            value={wall.extras.window_height_m ?? 1.2}
            onChange={(v) =>
              onUpdate((w) => ({
                ...w,
                extras: { ...w.extras, window_height_m: v },
              }))
            }
          />
          <DimInput
            label="Sill"
            value={wall.extras.window_sill_height_m ?? 0.9}
            onChange={(v) =>
              onUpdate((w) => ({
                ...w,
                extras: { ...w.extras, window_sill_height_m: v },
              }))
            }
          />
        </div>
      )}

      {/* Free-text notes */}
      <label className="block text-xs">
        <span className="block text-stone-500 mb-1">Notes (optional)</span>
        <input
          type="text"
          value={wall.userNotes}
          onChange={(e) =>
            onUpdate((w) => ({ ...w, userNotes: e.target.value }))
          }
          placeholder="alcove, partial wall, glass partition, …"
          className="w-full bg-stone-50 border border-stone-200 rounded-md px-3 py-1.5 text-stone-900 focus:border-stone-400 outline-none"
        />
      </label>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DimInput — accepts meters or feet syntax, displays both on blur.
// ---------------------------------------------------------------------------

interface DimInputProps {
  label: string;
  value: number;          // meters (canonical)
  onChange: (meters: number) => void;
}

function DimInput({ label, value, onChange }: DimInputProps) {
  const [text, setText] = useState<string>(value.toFixed(2));
  const [pristine, setPristine] = useState(true);

  // Re-sync when the canonical value changes (e.g., parent reset).
  useEffect(() => {
    if (pristine) setText(value.toFixed(2));
  }, [value, pristine]);

  return (
    <label className="block text-xs">
      <span className="block text-stone-500 mb-1">{label}</span>
      <input
        type="text"
        value={text}
        onChange={(e) => { setText(e.target.value); setPristine(false); }}
        onBlur={() => {
          const meters = parseFloat(text);
          if (Number.isFinite(meters) && meters > 0) {
            onChange(meters);
            setText(meters.toFixed(2));
          } else {
            setText(value.toFixed(2));
          }
          setPristine(true);
        }}
        className="w-full bg-stone-50 border border-stone-200 rounded-md px-3 py-1.5 text-stone-900 focus:border-stone-400 outline-none"
      />
      <span className="block text-[10px] text-stone-400 mt-0.5">
        {formatDim(value)}
      </span>
    </label>
  );
}

// ---------------------------------------------------------------------------

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${err.message} (HTTP ${err.status})`;
  if (err instanceof Error) return err.message;
  return fallback;
}
