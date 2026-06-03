"use client";

import { useMemo, useState } from "react";
import type { Fixture, Scene } from "@/lib/studio/types";

interface Props {
  scenes: Scene[];
  fixtures: Fixture[];
}

const CUSTOM_ID = "__custom";

const RENDER_SRC: Record<NonNullable<Scene["renderRef"]>, string> = {
  day: "/studio/renders/day.jpg",
  evening: "/studio/renders/evening.jpg",
  mood: "/studio/renders/mood.jpg",
};

export function SceneProgramming({ scenes, fixtures }: Props) {
  const allScenes = useMemo<Scene[]>(
    () => [
      ...scenes,
      {
        id: CUSTOM_ID,
        label: "+ Custom",
        description: "Build your own scene from scratch.",
        levels: {},
        renderRef: undefined,
      },
    ],
    [scenes],
  );

  const [sceneLevels, setSceneLevels] = useState<Record<string, Record<string, number>>>(() => {
    const init: Record<string, Record<string, number>> = {};
    for (const s of scenes) init[s.id] = { ...s.levels };
    init[CUSTOM_ID] = Object.fromEntries(fixtures.map((f) => [f.tag, 0]));
    return init;
  });

  const [activeSceneId, setActiveSceneId] = useState<string>(scenes[0]?.id ?? CUSTOM_ID);

  const activeScene = allScenes.find((s) => s.id === activeSceneId) ?? allScenes[0];
  const activeLevels = sceneLevels[activeSceneId] ?? {};

  const setLevel = (fixtureTag: string, level: number) => {
    setSceneLevels((prev) => ({
      ...prev,
      [activeSceneId]: { ...prev[activeSceneId], [fixtureTag]: level },
    }));
  };

  const reset = () => {
    if (activeSceneId === CUSTOM_ID) {
      setSceneLevels((prev) => ({
        ...prev,
        [CUSTOM_ID]: Object.fromEntries(fixtures.map((f) => [f.tag, 0])),
      }));
      return;
    }
    const original = scenes.find((s) => s.id === activeSceneId);
    if (original) {
      setSceneLevels((prev) => ({ ...prev, [activeSceneId]: { ...original.levels } }));
    }
  };

  const fullWattage = fixtures.reduce((s, f) => s + f.wattage * f.quantity, 0);
  const sceneWattage = fixtures.reduce(
    (s, f) => s + (f.wattage * f.quantity * (activeLevels[f.tag] ?? 0)) / 100,
    0,
  );

  const previewSrc = activeScene.renderRef ? RENDER_SRC[activeScene.renderRef] : undefined;

  return (
    <div className="bg-white border border-stone-200 rounded-md p-5">
      {/* Scene tabs */}
      <div className="flex gap-2 border-b border-stone-200 mb-5 overflow-x-auto">
        {allScenes.map((s) => {
          const isActive = s.id === activeSceneId;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setActiveSceneId(s.id)}
              className={
                isActive
                  ? "text-amber-700 border-b-2 border-amber-700 pb-2 px-3 text-sm font-medium whitespace-nowrap -mb-px"
                  : "text-stone-500 border-b-2 border-transparent hover:text-stone-900 hover:border-stone-300 pb-2 px-3 text-sm whitespace-nowrap -mb-px"
              }
            >
              {s.label}
            </button>
          );
        })}
      </div>

      <div className="grid sm:grid-cols-[260px_1fr] gap-6">
        {/* Left: preview */}
        <div>
          <div className="aspect-[4/3] bg-stone-100 rounded-md overflow-hidden border border-stone-200">
            {previewSrc ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={previewSrc}
                alt={`${activeScene.label} preview`}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-xs text-stone-400 italic">
                No preview
              </div>
            )}
          </div>
          {activeScene.description && (
            <div className="text-xs text-stone-500 italic mt-2">{activeScene.description}</div>
          )}
          <div className="text-xs text-stone-700 mt-3 space-y-1">
            <div>
              <span className="text-stone-400">Total:</span>{" "}
              <span className="tabular-nums">{Math.round(sceneWattage)} W</span>
            </div>
            <div className="text-stone-400">
              vs full: <span className="tabular-nums">{fullWattage} W</span>
            </div>
          </div>
          <button
            type="button"
            onClick={reset}
            className="text-xs text-amber-700 hover:text-amber-800 underline underline-offset-2 mt-3"
          >
            Reset to default
          </button>
        </div>

        {/* Right: fixture sliders */}
        <div className="space-y-0">
          {fixtures.map((f) => {
            const level = activeLevels[f.tag] ?? 0;
            return (
              <div
                key={f.tag}
                className="grid grid-cols-[auto_1fr_60px_40px] gap-3 items-center py-1 text-xs"
              >
                <div className="font-medium text-stone-900">{f.tag}</div>
                <div className="text-stone-500 truncate">{f.category}</div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={level}
                  onChange={(e) => setLevel(f.tag, Number(e.target.value))}
                  className="w-full accent-amber-700"
                  aria-label={`${f.tag} level`}
                />
                <div className="text-stone-700 text-right font-mono tabular-nums">{level}%</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
