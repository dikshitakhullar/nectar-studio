"use client";

import Link from "next/link";

export interface Step {
  href: string;
  label: string;
}

export const PROTO_STEPS: Step[] = [
  { href: "/studio/upload", label: "Upload" },
  { href: "/studio/rooms", label: "Rooms" },
  { href: "/studio/room-basics", label: "Room Basics" },
  { href: "/studio/walls", label: "Walls" },
  { href: "/studio/furniture", label: "Furniture" },
  { href: "/studio/brief", label: "Brief" },
  { href: "/studio/generating", label: "Generating" },
  { href: "/studio/pack", label: "Lighting Pack" },
];

interface StepNavProps {
  currentHref: string;
  /** Optional ?pid=&rid= suffix preserved across steps. */
  query?: string;
}

export function StepNav({ currentHref, query = "" }: StepNavProps) {
  const currentIndex = PROTO_STEPS.findIndex((s) => s.href === currentHref);
  return (
    <nav className="flex items-center gap-1 text-xs text-stone-500 mb-6 flex-wrap">
      {PROTO_STEPS.map((s, i) => {
        const href = query ? `${s.href}?${query}` : s.href;
        const tone =
          i === currentIndex
            ? "text-amber-700"
            : i < currentIndex
              ? "text-stone-700"
              : "";
        return (
          <div key={s.href} className="flex items-center">
            {i <= currentIndex ? (
              <Link href={href} className={tone}>
                {s.label}
              </Link>
            ) : (
              <span className={tone}>{s.label}</span>
            )}
            {i < PROTO_STEPS.length - 1 && <span className="mx-2 text-stone-300">›</span>}
          </div>
        );
      })}
    </nav>
  );
}
