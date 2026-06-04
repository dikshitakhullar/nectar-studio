"use client";

import type { Point } from "@/lib/api/types";

/** Width of the SVG box in CSS pixels. The container in the parent layout is
 * ~240px wide; we render at 220 to leave breathing room. */
const SVG_SIZE = 220;
const PADDING_RATIO = 0.1; // 10% padding around the polygon bbox.

const COLOR_STROKE = "#a8a29e"; // stone-400
const COLOR_STROKE_ACTIVE = "#b45309"; // amber-700
const COLOR_FILL = "#fef3c7"; // amber-100
const COLOR_LABEL = "#44403c"; // stone-700

export interface RoomMiniMapProps {
  polygon: Point[];
  /** Index of the currently-focused wall (the polygon edge i → i+1). */
  activeWallIndex: number | null;
  /** Letter labels for each wall, indexed by wall index. */
  wallLabels: string[];
  onSelectWall: (index: number) => void;
}

interface ProjectedPoint {
  x: number;
  y: number;
}

/**
 * Inline SVG plan view of the room polygon with N-arrow + wall letter labels.
 *
 * - Polygon is projected into the SVG viewBox so the bbox + 10% padding fits.
 * - The DXF/parser y-axis is mathematical (y up); we flip it so north reads up
 *   on screen.
 * - Each edge is a tappable group with a wide invisible hit area for easier
 *   clicking on small polygons.
 */
export function RoomMiniMap({
  polygon,
  activeWallIndex,
  wallLabels,
  onSelectWall,
}: RoomMiniMapProps) {
  if (polygon.length < 3) {
    return (
      <div className="bg-stone-100 border border-stone-200 rounded-md p-4 text-xs text-stone-500 text-center">
        Polygon unavailable
      </div>
    );
  }

  const { projected, viewBox } = projectPolygon(polygon, SVG_SIZE, PADDING_RATIO);
  const polylinePoints = projected.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg
      viewBox={viewBox}
      width={SVG_SIZE}
      height={SVG_SIZE}
      role="img"
      aria-label="Room mini-map"
      className="bg-white border border-stone-200 rounded-md"
    >
      {/* north arrow — sits in the top-left, in SVG-space coords */}
      <g transform={`translate(${SVG_SIZE * 0.06},${SVG_SIZE * 0.08})`}>
        <line
          x1={0}
          y1={SVG_SIZE * 0.06}
          x2={0}
          y2={0}
          stroke={COLOR_LABEL}
          strokeWidth={1.2}
        />
        <polygon
          points={`0,${-SVG_SIZE * 0.01} ${-SVG_SIZE * 0.015},${SVG_SIZE * 0.018} ${SVG_SIZE * 0.015},${SVG_SIZE * 0.018}`}
          fill={COLOR_LABEL}
        />
        <text
          x={0}
          y={SVG_SIZE * 0.085}
          textAnchor="middle"
          fontSize={SVG_SIZE * 0.05}
          fill={COLOR_LABEL}
          fontFamily="system-ui, sans-serif"
        >
          N
        </text>
      </g>

      {/* room fill */}
      <polygon
        points={polylinePoints}
        fill={COLOR_FILL}
        fillOpacity={0.4}
        stroke="none"
      />

      {/* edges */}
      {projected.map((p, i) => {
        const next = projected[(i + 1) % projected.length];
        const isActive = activeWallIndex === i;
        const midX = (p.x + next.x) / 2;
        const midY = (p.y + next.y) / 2;
        const label = wallLabels[i] ?? String(i + 1);
        return (
          <g
            key={i}
            onClick={() => onSelectWall(i)}
            style={{ cursor: "pointer" }}
          >
            {/* wide invisible hit target */}
            <line
              x1={p.x}
              y1={p.y}
              x2={next.x}
              y2={next.y}
              stroke="transparent"
              strokeWidth={SVG_SIZE * 0.06}
            />
            {/* visible stroke */}
            <line
              x1={p.x}
              y1={p.y}
              x2={next.x}
              y2={next.y}
              stroke={isActive ? COLOR_STROKE_ACTIVE : COLOR_STROKE}
              strokeWidth={isActive ? 3 : 2}
              strokeLinecap="round"
            />
            {/* label background dot for readability */}
            <circle
              cx={midX}
              cy={midY}
              r={SVG_SIZE * 0.038}
              fill="#ffffff"
              stroke={isActive ? COLOR_STROKE_ACTIVE : COLOR_STROKE}
              strokeWidth={1}
            />
            <text
              x={midX}
              y={midY + SVG_SIZE * 0.018}
              textAnchor="middle"
              fontSize={SVG_SIZE * 0.05}
              fontWeight={600}
              fill={isActive ? COLOR_STROKE_ACTIVE : COLOR_LABEL}
              fontFamily="system-ui, sans-serif"
              style={{ pointerEvents: "none" }}
            >
              {label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Project polygon into a square SVG viewBox, preserving aspect ratio.
 *
 * The DXF coordinate system has y-up; SVG has y-down, so we flip y to keep
 * north visually pointing up.
 */
function projectPolygon(
  polygon: Point[],
  size: number,
  paddingRatio: number,
): { projected: ProjectedPoint[]; viewBox: string } {
  let minX = polygon[0].x;
  let maxX = polygon[0].x;
  let minY = polygon[0].y;
  let maxY = polygon[0].y;
  for (const p of polygon) {
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }
  const w = Math.max(maxX - minX, 1e-6);
  const h = Math.max(maxY - minY, 1e-6);
  const pad = size * paddingRatio;
  const drawW = size - pad * 2;
  const drawH = size - pad * 2;
  const scale = Math.min(drawW / w, drawH / h);
  const offsetX = pad + (drawW - w * scale) / 2;
  const offsetY = pad + (drawH - h * scale) / 2;
  const projected: ProjectedPoint[] = polygon.map((p) => ({
    x: offsetX + (p.x - minX) * scale,
    // flip y: bigger source y → higher visually (smaller SVG y)
    y: size - (offsetY + (p.y - minY) * scale),
  }));
  const viewBox = `0 0 ${size} ${size}`;
  return { projected, viewBox };
}
