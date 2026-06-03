import type { SwitchingZone } from "@/lib/studio/types";

export function SwitchingDiagram({ zones }: { zones: SwitchingZone[] }) {
  return (
    <div className="space-y-3">
      {zones.map(z => (
        <div key={z.id} className="bg-white border border-stone-200 rounded-md p-4 grid sm:grid-cols-[auto_1fr_auto] gap-x-4 gap-y-1 items-baseline">
          <div className="text-amber-700 font-medium">{z.id}</div>
          <div>
            <div className="text-sm text-stone-900">{z.label}</div>
            <div className="text-xs text-stone-500 mt-1">Controls: {z.controlsTags.join(", ")}</div>
            <div className="text-xs text-stone-500">Switch: {z.switchLocation}</div>
          </div>
          <div className="text-xs">
            {z.dimmer ? <span className="text-amber-700">Dimmable</span> : <span className="text-stone-400">On/Off</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
