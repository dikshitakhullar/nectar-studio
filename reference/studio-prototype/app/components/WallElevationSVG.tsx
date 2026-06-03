"use client";

import type { WallId } from "@/lib/studio/types";
import { demoRoom, demoFixtures } from "@/lib/studio/demo-data";
import { computeWallSketch, type SketchedItem } from "@/lib/studio/wall-sketch";
import { fixturesForWall } from "@/lib/studio/fixtures";

// Architectural elevation palette
const STROKE_WALL = "#44403c";     // stone-700
const STROKE_FLOOR = "#1c1917";    // stone-900
const STROKE_ITEM = "#44403c";     // stone-700
const STROKE_DIM = "#a8a29e";      // stone-400
const STROKE_SCALE_FIG = "#a8a29e"; // stone-400 — scale figure
const FILL_FIXTURE = "#a16207";    // amber-700 — slightly warmer / less brown
const TEXT_LABEL = "#57534e";      // stone-600
const TEXT_DIM = "#78716c";        // stone-500
const HATCH_STROKE = "#d6d3d1";    // stone-300

export function WallElevationSVG({ wallId }: { wallId: WallId }) {
  const wall = demoRoom.walls[wallId];
  const sketch = computeWallSketch(wall, { widthPx: 600, paddingPx: 30 });
  const fixtures = fixturesForWall(demoFixtures, wallId);

  // Vertical layout:
  //   - dimension line at top inside padding (occupies top ~22px above wall outline)
  //   - wall ID label on top-left margin
  //   - floor line at outline bottom
  //   - extra room below for fixture tag labels & breathing room
  const topDimAreaPx = 28;
  const bottomMarginPx = 40;
  const totalH = sketch.outline.heightPx + sketch.outline.paddingPx + topDimAreaPx + bottomMarginPx;

  // Shift the entire wall outline down to leave room for top dimension line.
  const wallTopY = sketch.outline.paddingPx + topDimAreaPx;
  const wallLeftX = sketch.outline.paddingPx;
  const wallRightX = sketch.outline.paddingPx + sketch.outline.widthPx;
  const floorY = wallTopY + sketch.outline.heightPx;

  // Items are positioned by computeWallSketch in a coord system where wall top = paddingPx.
  // We need to shift them down by topDimAreaPx.
  const shiftItemY = (y: number) => y + topDimAreaPx;

  // Unique hatch pattern id per wall (in case multiple elevations render in same DOM).
  const hatchId = `hatch-${wallId}`;

  return (
    <svg
      viewBox={`0 0 600 ${totalH}`}
      className="w-full border border-stone-200 rounded-md bg-white"
    >
      <defs>
        <pattern
          id={hatchId}
          patternUnits="userSpaceOnUse"
          width={6}
          height={6}
          patternTransform="rotate(45)"
        >
          <line x1={0} y1={0} x2={0} y2={6} stroke={HATCH_STROKE} strokeWidth={0.5} />
        </pattern>
      </defs>

      {/* Wall ID label — top-left, architectural caps */}
      <text
        x={wallLeftX}
        y={18}
        fontSize={10}
        fill={TEXT_DIM}
        style={{ letterSpacing: "0.08em" }}
      >
        {wallId.toUpperCase()} WALL
      </text>

      {/* Dimension line — top, spans wall length */}
      <DimensionLine
        x1={wallLeftX}
        x2={wallRightX}
        y={wallTopY - 12}
        lengthFt={wall.lengthFt}
      />

      {/* Wall outline (top + sides — floor is drawn separately as the dominant line) */}
      <polyline
        points={`${wallLeftX},${floorY} ${wallLeftX},${wallTopY} ${wallRightX},${wallTopY} ${wallRightX},${floorY}`}
        fill="none"
        stroke={STROKE_WALL}
        strokeWidth={1}
        strokeLinecap="square"
        strokeLinejoin="miter"
      />

      {/* Floor line — the dominant ground plane */}
      <line
        x1={wallLeftX - 6}
        y1={floorY}
        x2={wallRightX + 6}
        y2={floorY}
        stroke={STROKE_FLOOR}
        strokeWidth={2}
        strokeLinecap="square"
      />

      {/* Wall items — line-work only, kind-specific symbology */}
      {sketch.items.map((it, i) => (
        <WallItemGlyph
          key={i}
          item={{ ...it, yPx: shiftItemY(it.yPx) }}
          hatchUrl={`url(#${hatchId})`}
        />
      ))}

      {/* Wall-mounted fixture markers */}
      {fixtures.map((f, idx) => {
        const xPx = wallLeftX + sketch.outline.widthPx * ((idx + 1) / (fixtures.length + 1));
        // Mount the fixture marker high on the wall — typical sconce/picture light height ~6.5ft
        const mountY = floorY - 6.5 * sketch.scale;
        return (
          <g key={f.tag}>
            {/* Dashed mount line from marker to floor — reads as a mount drop, not structural */}
            <line
              x1={xPx}
              y1={mountY}
              x2={xPx}
              y2={floorY}
              stroke={STROKE_DIM}
              strokeWidth={0.5}
              strokeDasharray="2 2"
            />
            {/* Fixture mount marker — slightly larger, with a thin outer ring for refinement */}
            <circle cx={xPx} cy={mountY} r={5} fill="#ffffff" stroke={FILL_FIXTURE} strokeWidth={0.8} />
            <circle cx={xPx} cy={mountY} r={2.5} fill={FILL_FIXTURE} />
            {/* Tag */}
            <text
              x={xPx}
              y={mountY - 10}
              fontSize={9}
              fill={TEXT_LABEL}
              textAnchor="middle"
              style={{ letterSpacing: "0.04em" }}
            >
              {f.tag}
            </text>
          </g>
        );
      })}

      {/* Scale figure — 1.78m (~5'10") on the right edge of the elevation.
          Establishes instant human scale, common architectural convention. */}
      <ScaleFigure
        anchorX={wallRightX - 22}
        floorY={floorY}
        scale={sketch.scale}
      />
    </svg>
  );
}

/* ---------------- Sub-components ---------------- */

function DimensionLine({
  x1,
  x2,
  y,
  lengthFt,
}: {
  x1: number;
  x2: number;
  y: number;
  lengthFt: number;
}) {
  const tickH = 4;
  return (
    <g>
      {/* End ticks */}
      <line x1={x1} y1={y - tickH} x2={x1} y2={y + tickH} stroke={STROKE_DIM} strokeWidth={0.75} />
      <line x1={x2} y1={y - tickH} x2={x2} y2={y + tickH} stroke={STROKE_DIM} strokeWidth={0.75} />
      {/* Main dimension line — break in middle for text */}
      <line x1={x1} y1={y} x2={(x1 + x2) / 2 - 18} y2={y} stroke={STROKE_DIM} strokeWidth={0.75} />
      <line x1={(x1 + x2) / 2 + 18} y1={y} x2={x2} y2={y} stroke={STROKE_DIM} strokeWidth={0.75} />
      {/* Arrow tips */}
      <polyline
        points={`${x1 + 5},${y - 2.5} ${x1},${y} ${x1 + 5},${y + 2.5}`}
        fill="none"
        stroke={STROKE_DIM}
        strokeWidth={0.75}
      />
      <polyline
        points={`${x2 - 5},${y - 2.5} ${x2},${y} ${x2 - 5},${y + 2.5}`}
        fill="none"
        stroke={STROKE_DIM}
        strokeWidth={0.75}
      />
      <text
        x={(x1 + x2) / 2}
        y={y + 3}
        fontSize={9}
        fill={TEXT_DIM}
        textAnchor="middle"
      >
        {lengthFt.toFixed(1)} ft
      </text>
    </g>
  );
}

/**
 * A thin architectural human silhouette ~1.78m / 5'10" tall.
 * Anchored at floor level on the right edge of the elevation.
 * Purpose: instant human scale reference — common architectural convention.
 */
function ScaleFigure({
  anchorX,
  floorY,
  scale,
}: {
  anchorX: number;
  floorY: number;
  scale: number;
}) {
  // Convert metric heights to ft for the sketch scale (sketch.scale is px-per-ft).
  const totalH = 5.83 * scale; // 5'10" / 1.78m
  const headR = Math.min(4, totalH * 0.045);
  const headCy = floorY - totalH + headR;
  const neckY = headCy + headR + 1;
  // Shoulders / hips coords
  const shoulderY = neckY + totalH * 0.06;
  const hipY = floorY - totalH * 0.45;
  const halfShoulder = totalH * 0.06;
  const halfHip = totalH * 0.05;
  const halfFoot = totalH * 0.04;

  // Simple symmetric silhouette path — head circle + body trapezoid + legs.
  // Drawn as separate elements for clarity.
  return (
    <g>
      {/* Head */}
      <circle
        cx={anchorX}
        cy={headCy}
        r={headR}
        fill="none"
        stroke={STROKE_SCALE_FIG}
        strokeWidth={0.6}
      />
      {/* Body — torso outline */}
      <path
        d={`
          M ${anchorX - halfShoulder} ${shoulderY}
          L ${anchorX + halfShoulder} ${shoulderY}
          L ${anchorX + halfHip} ${hipY}
          L ${anchorX - halfHip} ${hipY}
          Z
        `}
        fill="none"
        stroke={STROKE_SCALE_FIG}
        strokeWidth={0.6}
      />
      {/* Legs — two thin trapezoidal legs from hip to floor */}
      <path
        d={`
          M ${anchorX - halfHip} ${hipY}
          L ${anchorX - 0.5} ${hipY}
          L ${anchorX - 0.5} ${floorY}
          L ${anchorX - halfFoot} ${floorY}
          Z
        `}
        fill="none"
        stroke={STROKE_SCALE_FIG}
        strokeWidth={0.6}
      />
      <path
        d={`
          M ${anchorX + 0.5} ${hipY}
          L ${anchorX + halfHip} ${hipY}
          L ${anchorX + halfFoot} ${floorY}
          L ${anchorX + 0.5} ${floorY}
          Z
        `}
        fill="none"
        stroke={STROKE_SCALE_FIG}
        strokeWidth={0.6}
      />
      {/* Tiny height annotation under the figure */}
      <text
        x={anchorX}
        y={floorY + 10}
        fontSize={7}
        fill={TEXT_DIM}
        textAnchor="middle"
        style={{ letterSpacing: "0.04em" }}
      >
        5&apos;10&quot;
      </text>
    </g>
  );
}

function WallItemGlyph({
  item,
  hatchUrl,
}: {
  item: SketchedItem;
  hatchUrl: string;
}) {
  const { kind, xPx, yPx, widthPx, heightPx } = item;
  const x2 = xPx + widthPx;
  const y2 = yPx + heightPx;
  const cx = xPx + widthPx / 2;
  const cy = yPx + heightPx / 2;
  const stroke = STROKE_ITEM;
  const sw = 1;

  // Common outlined rectangle (no fill).
  const Outline = (
    <rect
      x={xPx}
      y={yPx}
      width={widthPx}
      height={heightPx}
      fill="none"
      stroke={stroke}
      strokeWidth={sw}
    />
  );

  if (kind === "door") {
    // Outlined rectangle + diagonal swing line from the hinge corner.
    // Hinge on the left side, swing line to top-right corner.
    return (
      <g>
        {Outline}
        <line
          x1={xPx}
          y1={y2}
          x2={x2}
          y2={yPx}
          stroke={stroke}
          strokeWidth={0.6}
        />
      </g>
    );
  }

  if (kind === "window") {
    // Outline + 3 horizontal mullion lines.
    const inset = 3;
    const innerH = heightPx - inset * 2;
    const lineYs = [yPx + inset + innerH * 0.25, yPx + inset + innerH * 0.5, yPx + inset + innerH * 0.75];
    return (
      <g>
        {Outline}
        {lineYs.map((ly, i) => (
          <line
            key={i}
            x1={xPx + inset}
            y1={ly}
            x2={x2 - inset}
            y2={ly}
            stroke={stroke}
            strokeWidth={0.5}
          />
        ))}
        {/* Central vertical mullion */}
        <line
          x1={cx}
          y1={yPx + inset}
          x2={cx}
          y2={y2 - inset}
          stroke={stroke}
          strokeWidth={0.5}
        />
      </g>
    );
  }

  if (kind === "tv") {
    // Outline + small stand at the bottom center.
    const standW = Math.min(widthPx * 0.3, 18);
    const standH = 3;
    return (
      <g>
        {Outline}
        <line
          x1={cx}
          y1={y2}
          x2={cx}
          y2={y2 + standH}
          stroke={stroke}
          strokeWidth={0.75}
        />
        <line
          x1={cx - standW / 2}
          y1={y2 + standH}
          x2={cx + standW / 2}
          y2={y2 + standH}
          stroke={stroke}
          strokeWidth={0.75}
        />
      </g>
    );
  }

  if (kind === "art") {
    // Outlined frame + diagonal cross indicating framed artwork.
    return (
      <g>
        {Outline}
        <line x1={xPx} y1={yPx} x2={x2} y2={y2} stroke={stroke} strokeWidth={0.5} />
        <line x1={x2} y1={yPx} x2={xPx} y2={y2} stroke={stroke} strokeWidth={0.5} />
      </g>
    );
  }

  if (kind === "mirror") {
    // Outline + faint 45° hatch fill.
    return (
      <g>
        <rect
          x={xPx}
          y={yPx}
          width={widthPx}
          height={heightPx}
          fill={hatchUrl}
          stroke={stroke}
          strokeWidth={sw}
        />
      </g>
    );
  }

  if (kind === "shelf" || kind === "built_in") {
    // Outline + horizontal divider lines = shelves.
    const shelves = Math.max(2, Math.floor(heightPx / 22));
    const lines = [];
    for (let i = 1; i < shelves; i++) {
      const ly = yPx + (heightPx * i) / shelves;
      lines.push(
        <line
          key={i}
          x1={xPx}
          y1={ly}
          x2={x2}
          y2={ly}
          stroke={stroke}
          strokeWidth={0.5}
        />,
      );
    }
    return (
      <g>
        {Outline}
        {lines}
      </g>
    );
  }

  if (kind === "console" || kind === "sideboard") {
    // Outline + 2 vertical dividers = drawer/door splits.
    const splitXs = [xPx + widthPx / 3, xPx + (widthPx * 2) / 3];
    return (
      <g>
        {Outline}
        {splitXs.map((sx, i) => (
          <line
            key={i}
            x1={sx}
            y1={yPx}
            x2={sx}
            y2={y2}
            stroke={stroke}
            strokeWidth={0.5}
          />
        ))}
        {/* Tiny handle indicators */}
        {splitXs.map((sx, i) => (
          <line
            key={`h-${i}`}
            x1={sx - 3}
            y1={cy}
            x2={sx + 3}
            y2={cy}
            stroke={stroke}
            strokeWidth={0.5}
          />
        ))}
      </g>
    );
  }

  // Fallback — plain outline.
  return Outline;
}
