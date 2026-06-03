"use client";

import { useState } from "react";

const SCENES = [
  { id: "day", label: "Day", caption: "Morning, daylight-driven. Artificial lights off." },
  { id: "evening", label: "Evening", caption: "All layers on, dimmable scene." },
  { id: "mood", label: "Mood", caption: "Pendant + accents only. Art wall hero." },
];

export function RenderGallery() {
  const [active, setActive] = useState("evening");
  const scene = SCENES.find(s => s.id === active)!;
  return (
    <div className="space-y-3">
      <div className="aspect-[4/3] bg-stone-100 rounded-md overflow-hidden border border-stone-200">
        <img
          src={`/studio/renders/${scene.id}.jpg`}
          alt={`${scene.label} scene render`}
          className="w-full h-full object-cover"
        />
      </div>
      <div className="flex gap-2">
        {SCENES.map(s => (
          <button
            key={s.id}
            type="button"
            onClick={() => setActive(s.id)}
            className={`flex-1 text-xs uppercase tracking-wider py-2 rounded-md border transition ${
              active === s.id
                ? "border-amber-700 text-amber-700 bg-amber-50"
                : "border-stone-200 text-stone-500 hover:border-stone-400"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
      <p className="text-xs text-stone-500">{scene.caption}</p>
    </div>
  );
}
