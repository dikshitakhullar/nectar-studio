import type { FixtureRow } from "@/lib/api/types";

export function FixtureScheduleTable({ rows }: { rows: FixtureRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="text-sm text-stone-500 bg-white border border-stone-200 rounded-md px-4 py-3">
        No fixtures returned by the engine.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto bg-white border border-stone-200 rounded-md">
      <table className="w-full text-xs">
        <thead className="bg-stone-100 text-stone-500 uppercase tracking-wider">
          <tr>
            <th className="text-left p-3">SKU</th>
            <th className="text-left p-3">Name</th>
            <th className="text-right p-3">Qty</th>
            <th className="text-right p-3">W</th>
            <th className="text-right p-3">Lumens</th>
            <th className="text-right p-3">CCT</th>
            <th className="text-right p-3">CRI</th>
            <th className="text-right p-3">Beam</th>
          </tr>
        </thead>
        <tbody className="text-stone-700">
          {rows.map((f) => (
            <tr key={f.sku} className="border-t border-stone-200 hover:bg-stone-50">
              <td className="p-3 font-medium text-stone-900">{f.sku}</td>
              <td className="p-3">{f.name}</td>
              <td className="p-3 text-right">{f.count}</td>
              <td className="p-3 text-right">{f.wattage_w}</td>
              <td className="p-3 text-right">{f.lumens}</td>
              <td className="p-3 text-right">{f.cct_k}K</td>
              <td className="p-3 text-right">{f.cri}</td>
              <td className="p-3 text-right">{f.beam_angle_deg}°</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
