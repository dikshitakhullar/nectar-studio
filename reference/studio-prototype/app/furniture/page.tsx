import Link from "next/link";
import { StepNav } from "../components/StepNav";
import { FurniturePlanSVG } from "../components/FurniturePlanSVG";
import { demoRoom } from "@/lib/studio/demo-data";

export default function FurniturePage() {
  return (
    <div className="space-y-6">
      <StepNav currentHref="/studio/furniture" />

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Furniture layout</h1>
        <p className="text-stone-600 text-sm">Where the big pieces sit. Drives where pendants hang, where task lights go.</p>
      </div>

      <FurniturePlanSVG room={demoRoom} />

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Pieces in this room</div>
        <ul className="text-sm text-stone-700 space-y-1">
          {demoRoom.furniture.map((f, i) => (
            <li key={i} className="flex justify-between bg-white border border-stone-200 rounded-md px-3 py-2">
              <span className="capitalize text-stone-900">{f.label ?? f.kind.replace("_", " ")}</span>
              <span className="text-stone-500 text-xs">{f.widthFt} × {f.depthFt} ft</span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-stone-500">In v1, drag and drop pieces onto the grid. Optional floor plan upload bypasses this entirely.</p>
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/art-lighting" className="text-sm text-stone-500 hover:text-stone-700">← Back</Link>
        <Link href="/studio/brief" className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition">
          Continue →
        </Link>
      </div>
    </div>
  );
}
