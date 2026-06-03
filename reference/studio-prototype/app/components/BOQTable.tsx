import type { BOQLine } from "@/lib/studio/types";
import { formatInr, sumByCategory, sumTotal } from "@/lib/studio/boq";

const CATEGORIES: BOQLine["category"][] = ["Decorative", "Architectural", "Controls", "Drivers/Accessories"];

export function BOQTable({ lines }: { lines: BOQLine[] }) {
  return (
    <div className="space-y-6">
      {CATEGORIES.map(cat => {
        const rows = lines.filter(l => l.category === cat);
        if (rows.length === 0) return null;
        return (
          <div key={cat} className="bg-white border border-stone-200 rounded-md overflow-hidden">
            <div className="bg-stone-100 px-4 py-2 text-xs uppercase tracking-wider text-amber-700/90 flex justify-between">
              <span>{cat}</span>
              <span className="text-stone-700">{formatInr(sumByCategory(lines, cat))}</span>
            </div>
            <table className="w-full text-xs">
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-t border-stone-200">
                    <td className="p-3 text-stone-700">{r.description}</td>
                    <td className="p-3 text-right text-stone-500 w-16">{r.qty}</td>
                    <td className="p-3 text-right text-stone-500 w-24">{formatInr(r.unitInr)}</td>
                    <td className="p-3 text-right text-stone-900 w-28 font-medium">{formatInr(r.totalInr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
      <div className="border-t border-amber-700/30 pt-4 flex justify-between text-sm">
        <span className="text-amber-700">Grand total</span>
        <span className="font-medium text-lg text-stone-900">{formatInr(sumTotal(lines))}</span>
      </div>
    </div>
  );
}
