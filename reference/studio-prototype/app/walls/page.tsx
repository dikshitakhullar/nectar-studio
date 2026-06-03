"use client";

import { useState } from "react";
import Link from "next/link";
import { StepNav } from "../components/StepNav";
import { WallSketchSVG } from "../components/WallSketchSVG";
import { demoRoom } from "@/lib/studio/demo-data";
import type { WallId } from "@/lib/studio/types";

const WALL_ORDER: WallId[] = ["north", "east", "south", "west"];
const WALL_LABELS: Record<WallId, string> = {
  north: "Wall 1: Front wall (with door)",
  east: "Wall 2: Window wall",
  south: "Wall 3: TV wall",
  west: "Wall 4: Art wall",
};

export default function WallsPage() {
  const [wallIdx, setWallIdx] = useState(0);
  const [openWalls, setOpenWalls] = useState<Record<WallId, boolean>>({
    north: false,
    east: false,
    south: false,
    west: false,
  });

  const wallId = WALL_ORDER[wallIdx];
  const wall = demoRoom.walls[wallId];
  const isOpen = openWalls[wallId];

  const setOpen = (open: boolean) =>
    setOpenWalls((prev) => ({ ...prev, [wallId]: open }));

  return (
    <div className="space-y-6">
      <StepNav currentHref="/studio/walls" />

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">
            {wallIdx + 1} of 4
          </div>
          <Link
            href="/studio/art-lighting"
            className="text-xs text-amber-700 hover:text-amber-800 underline underline-offset-2"
          >
            Skip wall verification (I have 3D renders) →
          </Link>
        </div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Walls</h1>
        <p className="text-stone-600 text-sm">
          Mark doors, windows, art, built-ins on each wall. Click between walls anytime — your changes persist.
        </p>
      </div>

      {/* Wall selector — pill tabs + prev/next */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1">
          {WALL_ORDER.map((w, i) => (
            <button
              key={w}
              type="button"
              onClick={() => setWallIdx(i)}
              className={`px-3 py-1 text-xs rounded-full border transition capitalize ${
                wallIdx === i
                  ? "border-amber-700 text-amber-700 bg-amber-50"
                  : "border-stone-200 text-stone-500 hover:border-stone-400 bg-white"
              }`}
            >
              {w}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setWallIdx(Math.max(0, wallIdx - 1))}
            disabled={wallIdx === 0}
            className="border border-stone-200 bg-white rounded-md w-8 h-8 text-stone-500 hover:border-stone-400 disabled:opacity-30 disabled:cursor-not-allowed transition"
            aria-label="Previous wall"
          >
            ←
          </button>
          <button
            type="button"
            onClick={() => setWallIdx(Math.min(WALL_ORDER.length - 1, wallIdx + 1))}
            disabled={wallIdx === WALL_ORDER.length - 1}
            className="border border-stone-200 bg-white rounded-md w-8 h-8 text-stone-500 hover:border-stone-400 disabled:opacity-30 disabled:cursor-not-allowed transition"
            aria-label="Next wall"
          >
            →
          </button>
        </div>
      </div>

      {/* Wall name + sketch (slides horizontally between walls) */}
      <div className="space-y-2">
        <div className="text-sm font-medium text-stone-900">{WALL_LABELS[wallId]}</div>
        <div className="overflow-hidden">
          <div
            className="flex transition-transform duration-300 ease-out"
            style={{ transform: `translateX(-${wallIdx * 100}%)` }}
          >
            {WALL_ORDER.map((w) => (
              <div key={w} className="min-w-full">
                <WallSketchSVG wall={demoRoom.walls[w]} isOpen={openWalls[w]} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* "This wall opens to another space" toggle (per-wall state) */}
      <label className="flex items-center gap-3 bg-white border border-stone-200 rounded-md px-4 py-3 cursor-pointer hover:border-stone-400 transition">
        <input
          type="checkbox"
          checked={isOpen}
          onChange={(e) => setOpen(e.target.checked)}
          className="rounded border-stone-300 text-amber-700 focus:ring-amber-700"
        />
        <div className="flex-1">
          <div className="text-sm font-medium text-stone-900">This wall opens to another space</div>
          <div className="text-xs text-stone-500 mt-0.5">No wall here — the room extends into the kitchen / hallway / next room.</div>
        </div>
      </label>

      {/* Items list / open placeholder */}
      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">
          What&apos;s on the {wallId} wall? (prototype: shown above)
        </div>
        {isOpen ? (
          <div className="text-sm text-stone-500 bg-white border border-dashed border-stone-300 rounded-md px-3 py-4 text-center">
            No items — this side is open
          </div>
        ) : (
          <ul className="text-sm text-stone-700 space-y-1">
            {wall.items.map((item, i) => (
              <li key={i} className="flex justify-between bg-white border border-stone-200 rounded-md px-3 py-2">
                <span className="capitalize text-stone-900">{item.kind.replace("_", " ")}</span>
                <span className="text-stone-500 text-xs">
                  {item.positionFromLeftFt} ft from left · {item.widthFt} ft wide
                  {item.notes ? ` · ${item.notes}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="text-xs text-stone-500">In v1, users tap to add doors, windows, TV, art etc., and the sketch updates live.</p>
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/room-basics" className="text-sm text-stone-500 hover:text-stone-700">
          ← Back to Room Basics
        </Link>
        <Link
          href="/studio/art-lighting"
          className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition"
        >
          Continue to furniture →
        </Link>
      </div>
    </div>
  );
}
