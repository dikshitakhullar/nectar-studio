"use client";

import { computeRCPLayout } from "@/lib/studio/rcp";
import { demoRoom, demoFixtures } from "@/lib/studio/demo-data";

const LAYER_COLOR: Record<string, string> = {
  ambient: "#ca8a04",
  task: "#0369a1",
  accent: "#be123c",
  decorative: "#7c3aed",
};

export function RCPDiagramSVG() {
  const layout = computeRCPLayout(demoRoom, demoFixtures, { widthPx: 700, paddingPx: 40 });
  const totalH = layout.outline.heightPx + 2 * layout.outline.paddingPx;

  return (
    <svg
      viewBox={`0 0 700 ${totalH}`}
      className="w-full border border-stone-200 rounded-md bg-white"
      role="img"
      aria-label="Reflected ceiling plan top-down"
    >
      <rect
        x={layout.outline.paddingPx}
        y={layout.outline.paddingPx}
        width={layout.outline.widthPx}
        height={layout.outline.heightPx}
        fill="none"
        stroke="#a8a29e"
        strokeWidth={1.5}
      />
      {/* Cove perimeter */}
      <rect
        x={layout.outline.paddingPx + 4}
        y={layout.outline.paddingPx + 4}
        width={layout.outline.widthPx - 8}
        height={layout.outline.heightPx - 8}
        fill="none"
        stroke="#a16207"
        strokeWidth={1}
        strokeDasharray="2 4"
        opacity={0.6}
      />
      {/* Openings (doors + windows) */}
      {layout.openings.map((o, i) => (
        <line
          key={i}
          x1={o.startPx.x}
          y1={o.startPx.y}
          x2={o.endPx.x}
          y2={o.endPx.y}
          stroke={o.kind === "door" ? "#92400e" : "#075985"}
          strokeWidth={4}
        />
      ))}
      {/* Fixtures */}
      {layout.fixtures.map(f => (
        <g key={f.tag}>
          <circle cx={f.xPx} cy={f.yPx} r={f.category.includes("Pendant") ? 10 : 7} fill={LAYER_COLOR[f.layer] ?? "#a8a29e"} opacity={0.9} />
          <text x={f.xPx} y={f.yPx - 12} fontSize={8} fill="#57534e" textAnchor="middle">{f.tag}</text>
        </g>
      ))}
      {/* Compass */}
      <text x={layout.outline.paddingPx} y={layout.outline.paddingPx - 12} fontSize={9} fill="#78716c">N (front door)</text>
    </svg>
  );
}
