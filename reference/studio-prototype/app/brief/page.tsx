import Link from "next/link";
import { StepNav } from "../components/StepNav";
import { OptionGroup } from "../components/AnswerOption";

export default function BriefPage() {
  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/brief" />

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Brief + constraints</h1>
        <p className="text-stone-600 text-sm">Usage, mood, anything the project can&apos;t do. Last step before generation.</p>
      </div>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">What happens in this room?</div>
        <OptionGroup
          multi
          options={[
            { id: "lounging", label: "Lounging / relaxing" },
            { id: "tv", label: "Watching TV / movies" },
            { id: "entertaining", label: "Hosting guests" },
            { id: "reading", label: "Reading" },
            { id: "wfh", label: "Working from home" },
            { id: "playing", label: "Kids playing" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Mood</div>
        <OptionGroup
          options={[
            { id: "cozy", label: "Cozy", description: "Soft, warm, restful" },
            { id: "bright", label: "Bright", description: "Energetic, clear" },
            { id: "dramatic", label: "Dramatic", description: "Layered, moody, accent-heavy" },
            { id: "mixed", label: "Mixed", description: "Different vibes at different times" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Primary usage time</div>
        <OptionGroup
          options={[
            { id: "morning", label: "Mornings" },
            { id: "evening", label: "Evenings" },
            { id: "mixed", label: "Mixed throughout the day" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Any constraints?</div>
        <OptionGroup
          multi
          options={[
            { id: "rented", label: "Rented property" },
            { id: "no_false_ceiling", label: "No false ceiling possible" },
            { id: "existing_wiring", label: "Existing wiring (can't change)" },
            { id: "heritage", label: "Heritage building" },
            { id: "none", label: "None of the above" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Anything else? (Optional)</div>
        <textarea
          placeholder="e.g. 'I want to highlight a specific painting on the west wall' or 'no exposed downlights please'"
          rows={3}
          className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
        />
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio/furniture" className="text-sm text-stone-500 hover:text-stone-700">← Back</Link>
        <Link href="/studio/generating" className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition">
          Generate my lighting plan →
        </Link>
      </div>
    </div>
  );
}
