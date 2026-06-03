import Link from "next/link";
import { StepNav } from "../components/StepNav";
import { demoProjectProfile } from "@/lib/studio/demo-data";

interface RoomEntry {
  id: string;
  label: string;
  status: "not_started" | "in_progress" | "done";
  detail?: string;
}

const ROOMS: RoomEntry[] = [
  { id: "living-tv", label: "Living / TV Room", status: "not_started", detail: "12 × 15 ft · East-facing window" },
];

const STATUS_LABELS: Record<RoomEntry["status"], string> = {
  not_started: "Not started",
  in_progress: "In progress",
  done: "Done",
};

const STATUS_COLORS: Record<RoomEntry["status"], string> = {
  not_started: "text-stone-400",
  in_progress: "text-amber-700",
  done: "text-emerald-700",
};

export default function RoomsPage() {
  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/rooms" />

      <div className="space-y-2">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Rooms</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">{demoProjectProfile.projectName}</h1>
        <p className="text-stone-600 text-sm">{demoProjectProfile.clientName} · Add rooms one at a time. We'll design each room with shared CCT and brand preferences from your Project Profile.</p>
      </div>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Rooms in this project</div>
        <div className="space-y-2">
          {ROOMS.map(room => (
            <Link
              key={room.id}
              href="/studio/room-basics"
              className="block bg-white border border-stone-200 rounded-md p-4 hover:border-amber-700 transition"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1">
                  <div className="text-sm font-medium text-stone-900">{room.label}</div>
                  {room.detail && <div className="text-xs text-stone-500 mt-1">{room.detail}</div>}
                </div>
                <div className="text-xs text-stone-500">
                  <span className={STATUS_COLORS[room.status]}>{STATUS_LABELS[room.status]}</span>
                </div>
                <div className="text-stone-400">→</div>
              </div>
            </Link>
          ))}
        </div>

        {/* Disabled add-room button with tooltip */}
        <div className="pt-2">
          <button
            type="button"
            disabled
            className="w-full border-2 border-dashed border-stone-200 rounded-md p-4 text-stone-400 cursor-not-allowed text-sm"
            title="Multi-room ships in v1.1 — for the prototype we focus on one room at a time"
          >
            + Add another room <span className="text-xs">(multi-room ships in v1.1)</span>
          </button>
        </div>
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/project-profile" className="text-sm text-stone-500 hover:text-stone-700">← Back to Project Profile</Link>
      </div>
    </div>
  );
}
