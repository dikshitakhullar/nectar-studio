import type { Fixture } from "@/lib/studio/types";

interface Props {
  fixtures: Fixture[];
}

export function BrandRecCard({ fixtures }: Props) {
  const archByCat = new Map<string, Fixture>();
  for (const f of fixtures) {
    if (f.source === "architectural_spec" && !archByCat.has(f.category)) {
      archByCat.set(f.category, f);
    }
  }

  return (
    <div className="grid sm:grid-cols-2 gap-3">
      {[...archByCat.values()].map(f => (
        <div key={f.category} className="bg-white border border-stone-200 rounded-md p-4 space-y-2">
          <div className="text-sm font-medium text-stone-900">{f.category}</div>
          <div className="text-xs text-stone-500">
            Spec: {f.wattage}W · {f.cct}K · {f.beamAngleDeg ? `${f.beamAngleDeg}° beam ·` : ""} {f.dimmable ? "dimmable" : "non-dimmable"}
          </div>
          <div className="space-y-1 pt-2">
            {f.brandPicks?.map(bp => (
              <div key={`${bp.tier}-${bp.brand}`} className="flex justify-between text-xs">
                <span className="text-stone-500 capitalize">{bp.tier}</span>
                <span className="text-stone-900">{bp.brand}{bp.model ? ` · ${bp.model}` : ""}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
