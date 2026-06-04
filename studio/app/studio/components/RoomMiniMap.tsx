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
const COLOR_FURNITURE = "#78350f"; // amber-900 — high-contrast on amber-100 fill

// Door + window symbol palette.
const COLOR_DOOR = "#d6d3d1"; // stone-300 — swing-arc + door-leaf line
const COLOR_WINDOW = "#78716c"; // stone-500 — double-line glazing strokes
const COLOR_OPENING_MASK = "#ffffff"; // matches the SVG background fill

// Door swing arc and leaf: render width is the projected wall-length scale
// applied to width_m. The leaf is drawn from the hinge-side endpoint to the
// open-position 90° away on the interior side.
const DOOR_LEAF_STROKE_W = 1.2;
const DOOR_ARC_STROKE_W = 1.0;
// Window double-line offset (in SVG pixels) from the wall centreline. Two
// parallel lines, one on each side of the wall stroke.
const WINDOW_LINE_OFFSET_PX = 1.6;
const WINDOW_STROKE_W = 1.2;
// Width of the opening-mask rectangle perpendicular to the wall. Slightly
// larger than the wall stroke so the wall break reads clearly. Pixels in
// the projected SVG frame.
const OPENING_MASK_THICKNESS_PX = 3.0;

/** Optional furniture marker rendered as a dot on the polygon.
 *
 * Coordinates are in the same local-meter frame as `polygon` (the parser's
 * region-shifted frame). Each entry gets a small filled circle with an
 * SVG `<title>` for hover tooltips.
 */
export interface FurnitureMarker {
  position: Point;
  label: string;
}

/** Door marker rendered as a swing-arc + leaf on its host wall. */
export interface DoorMarker {
  wallIndex: number;
  alongWall: number;       // 0-1 fraction along the polygon edge
  widthM: number;
  /** Display name for the destination room (used in <title> tooltip). When
   * omitted, the tooltip reads "Door (exterior)". */
  destinationLabel?: string;
}

/** Window marker rendered as two parallel strokes on its host wall. */
export interface WindowMarker {
  wallIndex: number;
  alongWall: number;
  widthM: number;
  isDoorWindow?: boolean;  // french-window / balcony-door variant
}

export interface RoomMiniMapProps {
  polygon: Point[];
  /** Index of the currently-focused wall (the polygon edge i → i+1). */
  activeWallIndex: number | null;
  /** Letter labels for each wall, indexed by wall index. */
  wallLabels: string[];
  onSelectWall: (index: number) => void;
  /** Optional furniture dots overlaid on the polygon. */
  furniture?: FurnitureMarker[];
  /** Optional door symbols (swing arc + wall break) on edges. */
  doors?: DoorMarker[];
  /** Optional window symbols (double parallel strokes) on edges. */
  windows?: WindowMarker[];
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
 * - Optional door/window markers render on top of the wall strokes — doors as
 *   a short break with a 90° swing arc into the room, windows as a parallel
 *   double-line on the wall.
 */
export function RoomMiniMap({
  polygon,
  activeWallIndex,
  wallLabels,
  onSelectWall,
  furniture,
  doors,
  windows,
}: RoomMiniMapProps) {
  if (polygon.length < 3) {
    return (
      <div className="bg-stone-100 border border-stone-200 rounded-md p-4 text-xs text-stone-500 text-center">
        Polygon unavailable
      </div>
    );
  }

  const { projected, viewBox, projectPoint } = projectPolygon(
    polygon, SVG_SIZE, PADDING_RATIO,
  );
  const polylinePoints = projected.map((p) => `${p.x},${p.y}`).join(" ");
  // Furniture dots reuse the same projection function used for the polygon
  // so the markers land on the right spot regardless of the polygon's bbox.
  const furnitureMarkers = furniture ?? [];
  const doorMarkers = doors ?? [];
  const windowMarkers = windows ?? [];

  // Polygon centroid in SVG space — used to decide which side of a wall is
  // interior so door swings and window line offsets point the right way.
  const centroidSvg: ProjectedPoint = {
    x: projected.reduce((s, p) => s + p.x, 0) / projected.length,
    y: projected.reduce((s, p) => s + p.y, 0) / projected.length,
  };

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

      {/* door + window symbols — drawn AFTER walls so they sit on top.
          BEFORE the wall-label dots are drawn though (the labels above are
          inside the edge map, so we draw openings after to overlap the wall
          stroke and the labels stay readable on top via their own white dot
          background). */}
      {doorMarkers.map((d, i) => {
        const symbol = computeDoorSymbol(
          polygon, projectPoint, centroidSvg, d,
        );
        if (symbol === null) return null;
        const tooltip = d.destinationLabel
          ? `Door (leads to ${d.destinationLabel})`
          : "Door (exterior)";
        return (
          <g key={`door-${i}`} aria-label={tooltip}>
            <title>{tooltip}</title>
            {/* wall break — a white rectangle masking the wall stroke */}
            <polygon
              points={symbol.maskPolygon}
              fill={COLOR_OPENING_MASK}
              stroke="none"
            />
            {/* door leaf — straight line from hinge to swing-open endpoint */}
            <line
              x1={symbol.hingeX}
              y1={symbol.hingeY}
              x2={symbol.leafEndX}
              y2={symbol.leafEndY}
              stroke={COLOR_DOOR}
              strokeWidth={DOOR_LEAF_STROKE_W}
              strokeLinecap="round"
            />
            {/* swing arc — quarter circle interior of the wall */}
            <path
              d={symbol.arcPath}
              fill="none"
              stroke={COLOR_DOOR}
              strokeWidth={DOOR_ARC_STROKE_W}
            />
          </g>
        );
      })}

      {windowMarkers.map((w, i) => {
        const symbol = computeWindowSymbol(
          polygon, projectPoint, centroidSvg, w,
        );
        if (symbol === null) return null;
        const widthLabel = `${w.widthM.toFixed(1)}m wide`;
        const tooltip = w.isDoorWindow
          ? `French window (${widthLabel})`
          : `Window (${widthLabel})`;
        return (
          <g key={`win-${i}`} aria-label={tooltip}>
            <title>{tooltip}</title>
            {/* wall break — same masking trick as doors */}
            <polygon
              points={symbol.maskPolygon}
              fill={COLOR_OPENING_MASK}
              stroke="none"
            />
            {/* two parallel strokes — one offset toward interior, one toward exterior */}
            <line
              x1={symbol.innerStartX}
              y1={symbol.innerStartY}
              x2={symbol.innerEndX}
              y2={symbol.innerEndY}
              stroke={COLOR_WINDOW}
              strokeWidth={WINDOW_STROKE_W}
              strokeLinecap="round"
            />
            <line
              x1={symbol.outerStartX}
              y1={symbol.outerStartY}
              x2={symbol.outerEndX}
              y2={symbol.outerEndY}
              stroke={COLOR_WINDOW}
              strokeWidth={WINDOW_STROKE_W}
              strokeLinecap="round"
            />
          </g>
        );
      })}

      {/* furniture dots — small filled circles with title tooltips.
          Rendered AFTER the walls so they sit on top visually. */}
      {furnitureMarkers.map((f, i) => {
        const p = projectPoint(f.position);
        return (
          <g key={`furn-${i}`}>
            <circle
              cx={p.x}
              cy={p.y}
              r={SVG_SIZE * 0.018}
              fill={COLOR_FURNITURE}
              stroke="#ffffff"
              strokeWidth={1}
            >
              <title>{f.label}</title>
            </circle>
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Geometry helpers — all in projected SVG-pixel space. Doors and windows
// share the same edge-projection logic; only the symbol math differs.
// ---------------------------------------------------------------------------

interface EdgeFrame {
  midX: number;
  midY: number;
  /** Unit vector ALONG the wall (vertex i → vertex i+1, in SVG space). */
  dirX: number;
  dirY: number;
  /** Unit vector perpendicular to the wall, pointing into the polygon. */
  intoX: number;
  intoY: number;
  /** Half-length of the opening in SVG pixels (clipped to half-wall-length). */
  halfWidthPx: number;
}

/** Project a wall-index + along_wall fraction + meter width into an SVG-space
 * frame. Returns null when the wall index is out of range or the polygon edge
 * is degenerate. */
function computeEdgeFrame(
  polygon: Point[],
  projectPoint: (p: Point) => ProjectedPoint,
  centroidSvg: ProjectedPoint,
  wallIndex: number,
  alongWall: number,
  widthM: number,
): EdgeFrame | null {
  if (wallIndex < 0 || wallIndex >= polygon.length) return null;
  const aSrc = polygon[wallIndex];
  const bSrc = polygon[(wallIndex + 1) % polygon.length];
  const a = projectPoint(aSrc);
  const b = projectPoint(bSrc);
  const edgeDx = b.x - a.x;
  const edgeDy = b.y - a.y;
  const edgeLen = Math.hypot(edgeDx, edgeDy);
  if (edgeLen <= 0) return null;

  const dirX = edgeDx / edgeLen;
  const dirY = edgeDy / edgeLen;

  // Position along the edge in SVG space
  const t = Math.max(0, Math.min(1, alongWall));
  const midX = a.x + edgeDx * t;
  const midY = a.y + edgeDy * t;

  // Convert width_m to SVG pixels using the same scale as the edge.
  // The edge spans the meter-length wallLengthM in `widthM`-per-meter SVG
  // pixels. We compute the meter length from the source polygon and use that
  // as the conversion factor.
  const wallLenM = Math.hypot(bSrc.x - aSrc.x, bSrc.y - aSrc.y);
  if (wallLenM <= 0) return null;
  const metersToPx = edgeLen / wallLenM;
  // Clip the door / window to the wall length: at most half the wall on each side.
  const halfWidthPx = Math.min(widthM * metersToPx / 2, edgeLen / 2);

  // Perpendicular: rotate (dirX, dirY) by 90°. Two candidates — pick the one
  // pointing toward the centroid.
  let perpX = -dirY;
  let perpY = dirX;
  const toCentroidX = centroidSvg.x - midX;
  const toCentroidY = centroidSvg.y - midY;
  if (perpX * toCentroidX + perpY * toCentroidY < 0) {
    perpX = -perpX;
    perpY = -perpY;
  }

  return {
    midX,
    midY,
    dirX,
    dirY,
    intoX: perpX,
    intoY: perpY,
    halfWidthPx,
  };
}

interface DoorSymbol {
  /** SVG polygon points string for the wall-break mask. */
  maskPolygon: string;
  hingeX: number;
  hingeY: number;
  leafEndX: number;
  leafEndY: number;
  /** SVG path d attribute for the swing arc (quarter circle). */
  arcPath: string;
}

function computeDoorSymbol(
  polygon: Point[],
  projectPoint: (p: Point) => ProjectedPoint,
  centroidSvg: ProjectedPoint,
  door: DoorMarker,
): DoorSymbol | null {
  const frame = computeEdgeFrame(
    polygon, projectPoint, centroidSvg,
    door.wallIndex, door.alongWall, door.widthM,
  );
  if (frame === null) return null;
  const { midX, midY, dirX, dirY, intoX, intoY, halfWidthPx } = frame;
  // Wall-break endpoints along the wall edge.
  const startX = midX - dirX * halfWidthPx;
  const startY = midY - dirY * halfWidthPx;
  const endX = midX + dirX * halfWidthPx;
  const endY = midY + dirY * halfWidthPx;

  // Mask: a thin rectangle straddling the wall, slightly into the interior
  // and slightly outside, so the wall stroke break reads clearly.
  const halfMask = OPENING_MASK_THICKNESS_PX / 2;
  const maskPolygon = [
    [startX - intoX * halfMask, startY - intoY * halfMask],
    [endX - intoX * halfMask, endY - intoY * halfMask],
    [endX + intoX * halfMask, endY + intoY * halfMask],
    [startX + intoX * halfMask, startY + intoY * halfMask],
  ]
    .map(([x, y]) => `${x},${y}`)
    .join(" ");

  // Hinge end = start; swing-open end = 90° from start into the interior, at
  // radius = door width (the full opening, not half).
  const radius = halfWidthPx * 2;
  const hingeX = startX;
  const hingeY = startY;
  const leafEndX = hingeX + intoX * radius;
  const leafEndY = hingeY + intoY * radius;
  // Quarter-circle arc from `endX,endY` (the other side of the opening, where
  // the door leaf would be when CLOSED on the wall — but conceptually we
  // arc from the closed position to the open position around the hinge.)
  //
  // We want a visual quarter-arc from the "closed" position (along the wall,
  // at endX,endY) sweeping into the room to the "open" position (leafEndX,
  // leafEndY). SVG arc: M endX,endY A radius,radius 0 0 sweep leafEndX,leafEndY.
  // Sweep flag chosen so the arc bulges into the interior — we determine it
  // by the cross product sign of (dir) x (into).
  const cross = dirX * intoY - dirY * intoX;
  const sweepFlag = cross > 0 ? 0 : 1;
  const arcPath = `M ${endX},${endY} A ${radius},${radius} 0 0 ${sweepFlag} ${leafEndX},${leafEndY}`;

  return { maskPolygon, hingeX, hingeY, leafEndX, leafEndY, arcPath };
}

interface WindowSymbol {
  maskPolygon: string;
  innerStartX: number;
  innerStartY: number;
  innerEndX: number;
  innerEndY: number;
  outerStartX: number;
  outerStartY: number;
  outerEndX: number;
  outerEndY: number;
}

function computeWindowSymbol(
  polygon: Point[],
  projectPoint: (p: Point) => ProjectedPoint,
  centroidSvg: ProjectedPoint,
  win: WindowMarker,
): WindowSymbol | null {
  const frame = computeEdgeFrame(
    polygon, projectPoint, centroidSvg,
    win.wallIndex, win.alongWall, win.widthM,
  );
  if (frame === null) return null;
  const { midX, midY, dirX, dirY, intoX, intoY, halfWidthPx } = frame;

  const startX = midX - dirX * halfWidthPx;
  const startY = midY - dirY * halfWidthPx;
  const endX = midX + dirX * halfWidthPx;
  const endY = midY + dirY * halfWidthPx;

  // Mask straddles the wall stroke so the two glazing lines read as a window
  // rather than crossing the wall stroke.
  const halfMask = OPENING_MASK_THICKNESS_PX / 2;
  const maskPolygon = [
    [startX - intoX * halfMask, startY - intoY * halfMask],
    [endX - intoX * halfMask, endY - intoY * halfMask],
    [endX + intoX * halfMask, endY + intoY * halfMask],
    [startX + intoX * halfMask, startY + intoY * halfMask],
  ]
    .map(([x, y]) => `${x},${y}`)
    .join(" ");

  // Two parallel lines, offset perpendicular to the wall by ± WINDOW_LINE_OFFSET_PX.
  const innerStartX = startX + intoX * WINDOW_LINE_OFFSET_PX;
  const innerStartY = startY + intoY * WINDOW_LINE_OFFSET_PX;
  const innerEndX = endX + intoX * WINDOW_LINE_OFFSET_PX;
  const innerEndY = endY + intoY * WINDOW_LINE_OFFSET_PX;
  const outerStartX = startX - intoX * WINDOW_LINE_OFFSET_PX;
  const outerStartY = startY - intoY * WINDOW_LINE_OFFSET_PX;
  const outerEndX = endX - intoX * WINDOW_LINE_OFFSET_PX;
  const outerEndY = endY - intoY * WINDOW_LINE_OFFSET_PX;

  return {
    maskPolygon,
    innerStartX, innerStartY, innerEndX, innerEndY,
    outerStartX, outerStartY, outerEndX, outerEndY,
  };
}

/** Project polygon into a square SVG viewBox, preserving aspect ratio.
 *
 * The DXF coordinate system has y-up; SVG has y-down, so we flip y to keep
 * north visually pointing up.
 *
 * Also returns a `projectPoint` closure so additional overlays (furniture
 * dots, doors, etc.) can land in the same projected frame as the polygon
 * without recomputing the bbox/scale.
 */
function projectPolygon(
  polygon: Point[],
  size: number,
  paddingRatio: number,
): {
  projected: ProjectedPoint[];
  viewBox: string;
  projectPoint: (p: Point) => ProjectedPoint;
} {
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
  const projectPoint = (p: Point): ProjectedPoint => ({
    x: offsetX + (p.x - minX) * scale,
    // flip y: bigger source y → higher visually (smaller SVG y)
    y: size - (offsetY + (p.y - minY) * scale),
  });
  const projected: ProjectedPoint[] = polygon.map(projectPoint);
  const viewBox = `0 0 ${size} ${size}`;
  return { projected, viewBox, projectPoint };
}
