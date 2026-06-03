"use client";

export interface Step {
  href: string;
  label: string;
}

export const PROTO_STEPS: Step[] = [
  { href: "/studio/upload", label: "Upload" },
  { href: "/studio/project-profile", label: "Project Profile" },
  { href: "/studio/rooms", label: "Rooms" },
  { href: "/studio/room-basics", label: "Room Basics" },
  { href: "/studio/walls", label: "Walls" },
  { href: "/studio/art-lighting", label: "Art" },
  { href: "/studio/furniture", label: "Furniture" },
  { href: "/studio/brief", label: "Brief" },
  { href: "/studio/generating", label: "Generating" },
  { href: "/studio/pack", label: "Lighting Pack" },
];

export function StepNav({ currentHref }: { currentHref: string }) {
  const currentIndex = PROTO_STEPS.findIndex((s) => s.href === currentHref);
  return (
    <nav className="flex items-center gap-1 text-xs text-stone-500 mb-6 flex-wrap">
      {PROTO_STEPS.map((s, i) => (
        <div key={s.href} className="flex items-center">
          <span
            className={
              i === currentIndex
                ? "text-amber-700"
                : i < currentIndex
                ? "text-stone-700"
                : ""
            }
          >
            {s.label}
          </span>
          {i < PROTO_STEPS.length - 1 && (
            <span className="mx-2 text-stone-300">›</span>
          )}
        </div>
      ))}
    </nav>
  );
}
