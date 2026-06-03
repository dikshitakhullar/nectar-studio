import Link from "next/link";
import { StepNav } from "../components/StepNav";
import { OptionGroup } from "../components/AnswerOption";
import { demoProjectProfile } from "@/lib/studio/demo-data";

export default function RoomBasicsPage() {
  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/room-basics" />

      <div className="bg-stone-100 border border-stone-200 rounded-md px-4 py-3 flex items-center justify-between text-sm">
        <div>
          <span className="text-stone-500">Designing:</span>{" "}
          <span className="text-stone-900 font-medium">Living / TV Room</span>
          <span className="text-stone-400"> · {demoProjectProfile.projectName}</span>
        </div>
        <Link href="/studio/rooms" className="text-xs text-amber-700 hover:text-amber-800">Back to rooms</Link>
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Room basics</h1>
        <p className="text-stone-600 text-sm">Geometry, ceiling, orientation, occupants. Skip if uploaded from floor plan.</p>
      </div>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Room type</div>
        <OptionGroup
          options={[
            { id: "living_tv", label: "Living / TV room" },
            { id: "drawing", label: "Drawing / formal living" },
            { id: "dining", label: "Dining room" },
            { id: "bedroom", label: "Bedroom" },
            { id: "kitchen", label: "Kitchen" },
            { id: "study", label: "Study / WFH" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Dimensions</div>
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Length (ft)", value: "15" },
            { label: "Width (ft)", value: "12" },
            { label: "Ceiling (ft)", value: "10" },
          ].map(f => (
            <label key={f.label} className="block">
              <div className="text-xs text-stone-500 mb-1">{f.label}</div>
              <input
                type="number"
                defaultValue={f.value}
                className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none"
              />
            </label>
          ))}
        </div>
        <p className="text-xs text-stone-500">Prototype: dimensions hardcoded for the demo room.</p>
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Ceiling type</div>
        <OptionGroup
          options={[
            { id: "false", label: "False ceiling" },
            { id: "flat", label: "Flat (no false ceiling)" },
            { id: "sloped", label: "Sloped" },
            { id: "mixed", label: "Mixed" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Main window faces</div>
        <OptionGroup
          options={[
            { id: "N", label: "North" },
            { id: "S", label: "South" },
            { id: "E", label: "East", description: "Morning sun" },
            { id: "W", label: "West", description: "Evening sun" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Who uses this room?</div>
        <OptionGroup
          multi
          options={[
            { id: "kids", label: "Kids" },
            { id: "young_adult", label: "Teen / young adult" },
            { id: "adult", label: "Adult (30s–50s)" },
            { id: "elderly", label: "Elderly", description: "Higher lux + glare control" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Floor + wall finish</div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-stone-500 mb-2">Floor</div>
            <OptionGroup
              options={[
                { id: "light", label: "Light" },
                { id: "mid", label: "Mid" },
                { id: "dark", label: "Dark" },
              ]}
            />
          </div>
          <div>
            <div className="text-xs text-stone-500 mb-2">Walls</div>
            <OptionGroup
              options={[
                { id: "light", label: "Light" },
                { id: "mid", label: "Mid" },
                { id: "dark", label: "Dark" },
              ]}
            />
          </div>
        </div>
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/project-profile" className="text-sm text-stone-500 hover:text-stone-700">← Back</Link>
        <Link href="/studio/walls" className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition">
          Continue to walls →
        </Link>
      </div>
    </div>
  );
}
