import { groupByLayer } from "@/lib/studio/fixtures";
import type { Fixture, LightingLayer } from "@/lib/studio/types";

const LAYER_LABELS: Record<LightingLayer, string> = {
  ambient: "Ambient",
  task: "Task",
  accent: "Accent",
  decorative: "Decorative",
};

const LAYER_DESCRIPTIONS: Record<LightingLayer, string> = {
  ambient: "General fill light. The first thing on when you walk in.",
  task: "Focused light for an activity — reading, cooking, working.",
  accent: "Highlights art, architecture, materials. Drama.",
  decorative: "Fixtures that are themselves the focal point.",
};

export function LayeredBreakdown({ fixtures }: { fixtures: Fixture[] }) {
  const grouped = groupByLayer(fixtures);
  const layers: LightingLayer[] = ["ambient", "task", "accent", "decorative"];

  return (
    <div className="grid sm:grid-cols-2 gap-4">
      {layers.map(layer => {
        const items = grouped[layer];
        if (items.length === 0) return null;
        return (
          <div key={layer} className="bg-white border border-stone-200 rounded-md p-4 space-y-3">
            <div>
              <div className="text-sm font-medium text-amber-700">{LAYER_LABELS[layer]}</div>
              <div className="text-xs text-stone-500">{LAYER_DESCRIPTIONS[layer]}</div>
            </div>
            <ul className="text-sm text-stone-700 space-y-1.5">
              {items.map(f => (
                <li key={f.tag} className="flex justify-between gap-3">
                  <span>
                    <span className="text-stone-400 mr-2">{f.tag}</span>
                    {f.category}
                  </span>
                  <span className="text-stone-500 text-xs whitespace-nowrap">
                    {f.quantity > 1 ? `${f.quantity} × ` : ""}{f.wattage}W
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
