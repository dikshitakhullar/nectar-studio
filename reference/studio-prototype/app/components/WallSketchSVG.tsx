"use client";

import type { Wall } from "@/lib/studio/types";
import { computeWallSketch } from "@/lib/studio/wall-sketch";

const FILL_BY_KIND: Record<string, string> = {
  door: "#92400e",
  window: "#075985",
  tv: "#1c1917",
  art: "#a16207",
  mirror: "#a8a29e",
  shelf: "#57534e",
  console: "#292524",
  sideboard: "#292524",
  built_in: "#57534e",
};

export function WallSketchSVG({ wall, isOpen }: { wall: Wall; isOpen?: boolean }) {
  const sketch = computeWallSketch(wall, { widthPx: 600, paddingPx: 30 });
  const totalHeight = sketch.outline.heightPx + 60;
  const open = isOpen ?? wall.isOpenBoundary ?? false;

  const x0 = sketch.outline.paddingPx;
  const y0 = sketch.outline.paddingPx;
  const w = sketch.outline.widthPx;
  const h = sketch.outline.heightPx;

  return (
    <svg
      viewBox={`0 0 600 ${totalHeight}`}
      className="w-full border border-stone-200 rounded-md bg-white"
      role="img"
      aria-label={`Sketch of ${wall.id} wall${open ? " (open boundary)" : ""}`}
    >
      {/* Floor line — always present, even for open boundary */}
      <line
        x1={x0}
        y1={y0 + h}
        x2={x0 + w}
        y2={y0 + h}
        stroke="#78716c"
        strokeWidth={1}
      />

      {open ? (
        <>
          {/* Open boundary: dotted top + sides, no items */}
          <line
            x1={x0}
            y1={y0}
            x2={x0 + w}
            y2={y0}
            stroke="#a8a29e"
            strokeWidth={1}
            strokeDasharray="2 4"
          />
          <line
            x1={x0}
            y1={y0}
            x2={x0}
            y2={y0 + h}
            stroke="#a8a29e"
            strokeWidth={1}
            strokeDasharray="2 4"
          />
          <line
            x1={x0 + w}
            y1={y0}
            x2={x0 + w}
            y2={y0 + h}
            stroke="#a8a29e"
            strokeWidth={1}
            strokeDasharray="2 4"
          />
          <text
            x={x0 + w / 2}
            y={y0 + 16}
            fontSize={10}
            fill="#78716c"
            textAnchor="middle"
          >
            Opens to adjacent space
          </text>
        </>
      ) : (
        <>
          {/* Wall outline */}
          <rect
            x={x0}
            y={y0}
            width={w}
            height={h}
            fill="none"
            stroke="#a8a29e"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
          {sketch.items.map((item, i) => (
            <g key={i}>
              <rect
                x={item.xPx}
                y={item.yPx}
                width={item.widthPx}
                height={item.heightPx}
                fill={FILL_BY_KIND[item.kind] ?? "#a8a29e"}
                opacity={0.9}
              />
              <text
                x={item.xPx + item.widthPx / 2}
                y={item.yPx + item.heightPx / 2 + 4}
                fontSize={9}
                fill="#fff"
                textAnchor="middle"
                opacity={0.9}
              >
                {item.kind}
              </text>
            </g>
          ))}
        </>
      )}
    </svg>
  );
}
