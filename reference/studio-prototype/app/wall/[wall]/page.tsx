"use client";

import Link from "next/link";
import { useParams, notFound } from "next/navigation";
import { useState } from "react";
import { StepNav } from "../../components/StepNav";
import { WallSketchSVG } from "../../components/WallSketchSVG";
import { demoRoom } from "@/lib/studio/demo-data";
import type { WallId } from "@/lib/studio/types";

const WALL_ORDER: WallId[] = ["north", "east", "south", "west"];
const WALL_LABELS: Record<WallId, string> = {
  north: "Wall 1: Front wall (with door)",
  east: "Wall 2: Window wall",
  south: "Wall 3: TV wall",
  west: "Wall 4: Art wall",
};

export default function WallPage() {
  const params = useParams();
  const wallParam = params.wall as string;
  const [isOpen, setIsOpen] = useState<boolean>(false);

  if (!WALL_ORDER.includes(wallParam as WallId)) notFound();
  const wallId = wallParam as WallId;
  const idx = WALL_ORDER.indexOf(wallId);
  const wall = demoRoom.walls[wallId];

  const nextHref = idx < WALL_ORDER.length - 1 ? `/studio/wall/${WALL_ORDER[idx + 1]}` : "/studio/art-lighting";
  const backHref = idx > 0 ? `/studio/wall/${WALL_ORDER[idx - 1]}` : "/studio/room-basics";

  return (
    <div className="space-y-6">
      <StepNav currentHref={`/studio/wall/${wallId}`} />

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">{idx + 1} of 4</div>
          <Link
            href="/studio/art-lighting"
            className="text-xs text-amber-700 hover:text-amber-800 underline underline-offset-2"
          >
            Skip wall verification (I have 3D renders) →
          </Link>
        </div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">{WALL_LABELS[wallId]}</h1>
        <p className="text-stone-600 text-sm">Mark doors, windows, art, built-ins. Live elevation updates as you go.</p>
      </div>

      <WallSketchSVG wall={wall} isOpen={isOpen} />

      <label className="flex items-center gap-3 bg-white border border-stone-200 rounded-md px-4 py-3 cursor-pointer hover:border-stone-400 transition">
        <input
          type="checkbox"
          checked={isOpen}
          onChange={(e) => setIsOpen(e.target.checked)}
          className="rounded border-stone-300 text-amber-700 focus:ring-amber-700"
        />
        <div className="flex-1">
          <div className="text-sm font-medium text-stone-900">This wall opens to another space</div>
          <div className="text-xs text-stone-500 mt-0.5">No wall here — the room extends into the kitchen / hallway / next room.</div>
        </div>
      </label>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">What&apos;s on this wall? (prototype: shown above)</div>
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
        <Link href={backHref} className="text-sm text-stone-500 hover:text-stone-700">← Back</Link>
        <Link href={nextHref} className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition">
          {idx < WALL_ORDER.length - 1 ? "Next wall →" : "Continue to furniture →"}
        </Link>
      </div>
    </div>
  );
}
