"use client";

import type { FurniturePiece, Room, Wall, WallId, WallItem } from "@/lib/studio/types";

const PADDING = 36;
const CANVAS_WIDTH = 600;

// Architectural palette — line-only, light luxury
const STROKE_ROOM = "#44403c";     // stone-700 — dominant room outline
const STROKE_FURN = "#44403c";     // stone-700 — furniture outlines
const STROKE_FURN_SOFT = "#78716c"; // stone-500 — cushion / divider lines
const STROKE_FURN_FAINT = "#a8a29e"; // stone-400 — finer dividers (drawers, shelves)
const STROKE_DOOR = "#a16207";     // amber-700 — door swing arc (subtle accent)
const STROKE_WINDOW = "#a8a29e";   // stone-400 — window inner parallel
const TEXT_LABEL = "#78716c";      // stone-500
const TEXT_COMPASS = "#a8a29e";    // stone-400

export function FurniturePlanSVG({ room }: { room: Room }) {
  const scale = (CANVAS_WIDTH - 2 * PADDING) / room.lengthFt;
  const roomWidthPx = room.lengthFt * scale;
  const roomHeightPx = room.widthFt * scale;
  const totalHeight = roomHeightPx + 2 * PADDING;

  const roomLeftX = PADDING;
  const roomTopY = PADDING;
  const roomRightX = PADDING + roomWidthPx;
  const roomBottomY = PADDING + roomHeightPx;

  return (
    <svg
      viewBox={`0 0 ${CANVAS_WIDTH} ${totalHeight}`}
      className="w-full border border-stone-200 rounded-md bg-white"
      role="img"
      aria-label="Top-down furniture plan"
    >
      {/* Room outline — dominant line weight */}
      <rect
        x={roomLeftX}
        y={roomTopY}
        width={roomWidthPx}
        height={roomHeightPx}
        fill="none"
        stroke={STROKE_ROOM}
        strokeWidth={1.75}
      />

      {/* Wall openings (doors + windows) — break the room outline and add swing arcs */}
      {(Object.keys(room.walls) as WallId[]).map((wallId) =>
        room.walls[wallId].items
          .filter((it) => it.kind === "door" || it.kind === "window")
          .map((it, i) => (
            <WallOpening
              key={`${wallId}-${i}`}
              wallId={wallId}
              wall={room.walls[wallId]}
              item={it}
              scale={scale}
              roomLeftX={roomLeftX}
              roomTopY={roomTopY}
              roomRightX={roomRightX}
              roomBottomY={roomBottomY}
            />
          )),
      )}

      {/* Furniture — top-down architectural symbology */}
      {room.furniture.map((f, i) => (
        <g key={i}>
          {renderFurniture(f, scale, PADDING)}
          {/* Label sits ABOVE the piece (small, stone-500) */}
          <text
            x={PADDING + f.positionXFt * scale}
            y={PADDING + f.positionYFt * scale - (f.depthFt * scale) / 2 - 4}
            fontSize={8}
            fill={TEXT_LABEL}
            textAnchor="middle"
            style={{ letterSpacing: "0.04em" }}
          >
            {(f.label ?? f.kind.replace("_", " ")).toUpperCase()}
          </text>
        </g>
      ))}

      {/* Compass — just outside the room outline, top-left for N, mid-right for E */}
      <text
        x={roomLeftX - 4}
        y={roomTopY - 10}
        fontSize={10}
        fill={TEXT_COMPASS}
        style={{ letterSpacing: "0.12em" }}
      >
        N
      </text>
      <text
        x={roomRightX + 8}
        y={roomTopY + roomHeightPx / 2 + 3}
        fontSize={10}
        fill={TEXT_COMPASS}
        style={{ letterSpacing: "0.12em" }}
      >
        E
      </text>

      {/* Subtle dimension hints — room length under bottom edge, width on left edge */}
      <text
        x={roomLeftX + roomWidthPx / 2}
        y={roomBottomY + 18}
        fontSize={9}
        fill={TEXT_COMPASS}
        textAnchor="middle"
      >
        {room.lengthFt.toFixed(0)}&apos; — 0&quot;
      </text>
      <text
        x={roomLeftX - 12}
        y={roomTopY + roomHeightPx / 2}
        fontSize={9}
        fill={TEXT_COMPASS}
        textAnchor="middle"
        transform={`rotate(-90 ${roomLeftX - 12} ${roomTopY + roomHeightPx / 2})`}
      >
        {room.widthFt.toFixed(0)}&apos; — 0&quot;
      </text>
    </svg>
  );
}

/* ---------------- Furniture symbology ---------------- */

function renderFurniture(piece: FurniturePiece, scale: number, padding: number) {
  const cx = padding + piece.positionXFt * scale;
  const cy = padding + piece.positionYFt * scale;
  const w = piece.widthFt * scale;
  const d = piece.depthFt * scale;
  const x = cx - w / 2;
  const y = cy - d / 2;

  switch (piece.kind) {
    case "sofa":
      // Outlined rect + cushion division lines + back-bar along the "north" edge.
      // The back-bar reads as the back of the sofa (facing toward room center).
      return (
        <g>
          <rect x={x} y={y} width={w} height={d} fill="none" stroke={STROKE_FURN} strokeWidth={1.2} />
          {/* Cushion divisions */}
          {piece.widthFt >= 6 ? (
            <>
              <line x1={x + w / 3} y1={y} x2={x + w / 3} y2={y + d} stroke={STROKE_FURN_SOFT} strokeWidth={0.6} />
              <line x1={x + (2 * w) / 3} y1={y} x2={x + (2 * w) / 3} y2={y + d} stroke={STROKE_FURN_SOFT} strokeWidth={0.6} />
            </>
          ) : (
            <line x1={x + w / 2} y1={y} x2={x + w / 2} y2={y + d} stroke={STROKE_FURN_SOFT} strokeWidth={0.6} />
          )}
          {/* Back-bar — inset along the "north" edge (lower y) */}
          <line
            x1={x + 4}
            y1={y + d * 0.15}
            x2={x + w - 4}
            y2={y + d * 0.15}
            stroke={STROKE_FURN_SOFT}
            strokeWidth={0.6}
          />
        </g>
      );

    case "armchair":
      // Rounded outlined rect, back-bar, and arm indicators down the sides.
      return (
        <g>
          <rect
            x={x}
            y={y}
            width={w}
            height={d}
            rx={3}
            ry={3}
            fill="none"
            stroke={STROKE_FURN}
            strokeWidth={1.2}
          />
          {/* Back-bar (top edge inset) */}
          <line
            x1={x + 4}
            y1={y + d * 0.22}
            x2={x + w - 4}
            y2={y + d * 0.22}
            stroke={STROKE_FURN_SOFT}
            strokeWidth={0.6}
          />
          {/* Arm indicators */}
          <line
            x1={x + 4}
            y1={y + d * 0.22}
            x2={x + 4}
            y2={y + d - 4}
            stroke={STROKE_FURN_SOFT}
            strokeWidth={0.6}
          />
          <line
            x1={x + w - 4}
            y1={y + d * 0.22}
            x2={x + w - 4}
            y2={y + d - 4}
            stroke={STROKE_FURN_SOFT}
            strokeWidth={0.6}
          />
        </g>
      );

    case "coffee_table":
    case "side_table":
    case "dining_table":
      // Outlined rect with slightly rounded corners — simple wood-tone outline.
      return (
        <rect
          x={x}
          y={y}
          width={w}
          height={d}
          rx={2}
          ry={2}
          fill="none"
          stroke={STROKE_FURN}
          strokeWidth={1.2}
        />
      );

    case "tv_console":
      // Long thin outlined rect with 2 vertical divider lines (drawer indications).
      return (
        <g>
          <rect x={x} y={y} width={w} height={d} fill="none" stroke={STROKE_FURN} strokeWidth={1.2} />
          <line
            x1={x + w / 3}
            y1={y}
            x2={x + w / 3}
            y2={y + d}
            stroke={STROKE_FURN_FAINT}
            strokeWidth={0.5}
          />
          <line
            x1={x + (2 * w) / 3}
            y1={y}
            x2={x + (2 * w) / 3}
            y2={y + d}
            stroke={STROKE_FURN_FAINT}
            strokeWidth={0.5}
          />
        </g>
      );

    case "bookshelf":
      // Outlined rect + horizontal shelf divider lines.
      return (
        <g>
          <rect x={x} y={y} width={w} height={d} fill="none" stroke={STROKE_FURN} strokeWidth={1.2} />
          <line x1={x} y1={y + d * 0.25} x2={x + w} y2={y + d * 0.25} stroke={STROKE_FURN_FAINT} strokeWidth={0.5} />
          <line x1={x} y1={y + d * 0.5} x2={x + w} y2={y + d * 0.5} stroke={STROKE_FURN_FAINT} strokeWidth={0.5} />
          <line x1={x} y1={y + d * 0.75} x2={x + w} y2={y + d * 0.75} stroke={STROKE_FURN_FAINT} strokeWidth={0.5} />
        </g>
      );

    case "bed":
      // Outlined rect + pillow indicators at the head ("north" edge).
      return (
        <g>
          <rect x={x} y={y} width={w} height={d} fill="none" stroke={STROKE_FURN} strokeWidth={1.2} />
          <ellipse
            cx={x + w * 0.3}
            cy={y + d * 0.12}
            rx={w * 0.15}
            ry={d * 0.06}
            fill="none"
            stroke={STROKE_FURN_SOFT}
            strokeWidth={0.5}
          />
          <ellipse
            cx={x + w * 0.7}
            cy={y + d * 0.12}
            rx={w * 0.15}
            ry={d * 0.06}
            fill="none"
            stroke={STROKE_FURN_SOFT}
            strokeWidth={0.5}
          />
        </g>
      );

    default:
      return <rect x={x} y={y} width={w} height={d} fill="none" stroke={STROKE_FURN} strokeWidth={1.2} />;
  }
}

/* ---------------- Wall openings (doors + windows) ---------------- */

interface WallOpeningProps {
  wallId: WallId;
  wall: Wall;
  item: WallItem;
  scale: number;
  roomLeftX: number;
  roomTopY: number;
  roomRightX: number;
  roomBottomY: number;
}

/**
 * Renders a door or window on the room outline. The wall outline rect already
 * covers the perimeter — we draw a white "break" segment on top, then add the
 * door swing arc or window parallel line.
 *
 * Wall coordinate convention (positionFromLeftFt):
 *   - north wall: left-to-right along the top edge (low y)
 *   - east wall: top-to-bottom along the right edge (high x)
 *   - south wall: left-to-right along the bottom edge (high y) — note: from "left" as you face the wall from inside
 *   - west wall: top-to-bottom along the left edge (low x)
 *
 * For top-down view we treat north as the top edge, etc.
 */
function WallOpening({
  wallId,
  wall,
  item,
  scale,
  roomLeftX,
  roomTopY,
  roomRightX,
  roomBottomY,
}: WallOpeningProps) {
  const openingPx = item.widthFt * scale;
  const offsetPx = item.positionFromLeftFt * scale;

  // Compute endpoints of the opening (start, end) along the wall and the
  // interior-facing inward direction (unit vector).
  let p1x = 0;
  let p1y = 0;
  let p2x = 0;
  let p2y = 0;
  let inwardX = 0;
  let inwardY = 0;

  switch (wallId) {
    case "north":
      p1x = roomLeftX + offsetPx;
      p1y = roomTopY;
      p2x = roomLeftX + offsetPx + openingPx;
      p2y = roomTopY;
      inwardY = 1; // into the room = down
      break;
    case "east":
      p1x = roomRightX;
      p1y = roomTopY + offsetPx;
      p2x = roomRightX;
      p2y = roomTopY + offsetPx + openingPx;
      inwardX = -1; // into the room = left
      break;
    case "south":
      // "left" while facing the wall from inside the room — flip so left=room's right side
      p1x = roomRightX - offsetPx;
      p1y = roomBottomY;
      p2x = roomRightX - offsetPx - openingPx;
      p2y = roomBottomY;
      inwardY = -1; // into the room = up
      break;
    case "west":
      p1x = roomLeftX;
      p1y = roomBottomY - offsetPx;
      p2x = roomLeftX;
      p2y = roomBottomY - offsetPx - openingPx;
      inwardX = 1; // into the room = right
      break;
  }

  // White "break" over the wall outline at the opening so the room rect doesn't
  // visually cross through the door/window.
  const isDoor = item.kind === "door";
  const breakLine = (
    <line
      x1={p1x}
      y1={p1y}
      x2={p2x}
      y2={p2y}
      stroke="#ffffff"
      strokeWidth={3}
    />
  );

  if (isDoor) {
    // Door swing — quarter-circle arc from hinge (p1) into the room.
    // The leaf swings from along-the-wall (towards p2) to inward.
    // Arc endpoint = hinge + opening width in the inward direction.
    const ax = p1x + inwardX * openingPx;
    const ay = p1y + inwardY * openingPx;
    // Door leaf (thin line) from hinge to the open position (the arc's endpoint at p2).
    const leafX = p2x;
    const leafY = p2y;
    return (
      <g>
        {breakLine}
        {/* Door leaf — thin line indicating the open door */}
        <line
          x1={p1x}
          y1={p1y}
          x2={leafX}
          y2={leafY}
          stroke={STROKE_DOOR}
          strokeWidth={0.8}
        />
        {/* Quarter-circle swing arc from leaf-open back into the room */}
        <path
          d={`M ${leafX} ${leafY} A ${openingPx} ${openingPx} 0 0 1 ${ax} ${ay}`}
          fill="none"
          stroke={STROKE_DOOR}
          strokeWidth={0.7}
        />
      </g>
    );
  }

  // Window — two parallel lines (one on the wall outline, one offset toward interior).
  const inset = 4;
  const inX1 = p1x + inwardX * inset;
  const inY1 = p1y + inwardY * inset;
  const inX2 = p2x + inwardX * inset;
  const inY2 = p2y + inwardY * inset;
  return (
    <g>
      {breakLine}
      {/* Outer window line — replaces the wall outline at the opening */}
      <line x1={p1x} y1={p1y} x2={p2x} y2={p2y} stroke={STROKE_ROOM} strokeWidth={1} />
      {/* Inner parallel — indicates glass */}
      <line x1={inX1} y1={inY1} x2={inX2} y2={inY2} stroke={STROKE_WINDOW} strokeWidth={0.7} />
    </g>
  );
}
