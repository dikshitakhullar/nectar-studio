import Link from "next/link";
import { StepNav } from "../components/StepNav";
import { OptionGroup } from "../components/AnswerOption";

export default function ProjectProfilePage() {
  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/project-profile" />

      <div className="space-y-2">
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Project profile</h1>
        <p className="text-stone-600 text-sm">One-time per project. Drives consistency across rooms.</p>
      </div>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Client</div>
        <div className="grid sm:grid-cols-2 gap-3">
          <label className="block">
            <div className="text-xs text-stone-500 mb-1">Client name</div>
            <input
              type="text"
              defaultValue="Mr. & Mrs. Sharma"
              placeholder="e.g. Mr. & Mrs. Sharma"
              className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
            />
          </label>
          <label className="block">
            <div className="text-xs text-stone-500 mb-1">Project name</div>
            <input
              type="text"
              defaultValue="Vasant Vihar Penthouse"
              placeholder="e.g. Vasant Vihar Penthouse"
              className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
            />
          </label>
        </div>
        <label className="block">
          <div className="text-xs text-stone-500 mb-1">Project location (optional)</div>
          <input
            type="text"
            defaultValue="Delhi"
            placeholder="City"
            className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm placeholder-stone-400 text-stone-900 focus:border-stone-400 outline-none"
          />
        </label>
        <p className="text-xs text-stone-500">Client name + project name appear on Client view headers.</p>
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">House type</div>
        <OptionGroup
          options={[
            { id: "apartment", label: "Apartment" },
            { id: "builder_floor", label: "Builder floor" },
            { id: "villa", label: "Villa" },
            { id: "standalone", label: "Standalone home" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Stage of construction</div>
        <OptionGroup
          options={[
            { id: "new_build", label: "New build", description: "Wiring not done yet" },
            { id: "mid_renovation", label: "Mid renovation", description: "Some flexibility on points" },
            { id: "lived_in", label: "Lived in", description: "Working with what exists" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Preferred ambient warmth</div>
        <OptionGroup
          options={[
            { id: "warm_2700", label: "Warm (2700K)", description: "Cozy, golden, restful" },
            { id: "neutral_3000", label: "Neutral (3000K)", description: "Balanced, contemporary" },
            { id: "mixed", label: "Mixed by room", description: "Warmer in lounges, cooler in kitchen" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Budget tier (architectural fixtures)</div>
        <OptionGroup
          options={[
            { id: "budget", label: "Budget", description: "Goldmedal, Polycab range" },
            { id: "mid", label: "Mid", description: "Wipro Garnet, Crompton" },
            { id: "premium", label: "Premium", description: "Philips, Schneider" },
            { id: "luxury", label: "Luxury", description: "Astera, imported" },
          ]}
        />
      </section>

      <div className="border-t border-stone-200 pt-6">
        <p className="text-xs uppercase tracking-wider text-stone-500 mb-2">Install + controls (optional — skip and we&apos;ll use sensible defaults)</p>
        <p className="text-xs text-stone-500">These shape your install notes and switching plan. Skip if you don&apos;t know yet — the agent picks sensible defaults and you can refine after seeing the first plan.</p>
      </div>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Smart home <span className="text-stone-400 normal-case tracking-normal">(optional)</span></div>
        <h3 className="text-sm text-stone-600">Which ecosystem the scenes will live in. Determines which switches / keypads we can spec.</h3>
        <OptionGroup
          options={[
            { id: "none", label: "None — manual switches only" },
            { id: "maybe_later", label: "Maybe later — keep wiring smart-ready" },
            { id: "lutron_caseta", label: "Lutron Caséta", description: "Most reliable, premium" },
            { id: "apple_home", label: "Apple Home / HomeKit" },
            { id: "google", label: "Google Home" },
            { id: "smartthings", label: "Samsung SmartThings" },
            { id: "homeassistant", label: "Home Assistant", description: "Open-source, self-hosted" },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Dimming protocol <span className="text-stone-400 normal-case tracking-normal">(optional)</span></div>
        <h3 className="text-sm text-stone-600">How the dimmers talk to the fixtures. Affects driver compatibility and install cost.</h3>
        <OptionGroup
          options={[
            { id: "triac", label: "TRIAC (forward-phase)", description: "Cheap, works with existing wall dimmers. Often flickers with LED — verify compatibility per fixture." },
            { id: "elv", label: "ELV (reverse-phase)", description: "Better for LED. Smooth dim curve. Common in mid-tier residential." },
            { id: "0-10v", label: "0–10V (analog)", description: "Professional-grade. Needs 2 extra wires. Smooth to 1%. Common in high-end residential and offices." },
            { id: "dali", label: "DALI (digital)", description: "Polarity-free 2-wire bus. Up to 64 addressable fixtures per loop. Re-zone in software. Premium." },
            { id: "zigbee", label: "Zigbee (wireless mesh)", description: "No control wires — mains power only. Ideal for retrofits. Some 2.4GHz interference risk." },
            { id: "lutron", label: "Lutron RadioRA / HomeWorks", description: "Premium ecosystem. Best driver compatibility. Native scene controllers. Higher cost." },
          ]}
        />
      </section>

      <section className="space-y-3">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Maintenance ability <span className="text-stone-400 normal-case tracking-normal">(optional)</span></div>
        <h3 className="text-sm text-stone-600">Who replaces a failed driver or bulb. Drives how adventurous we can get with fixture life.</h3>
        <OptionGroup
          options={[
            { id: "diy", label: "DIY", description: "Owner replaces bulbs / dimmers themselves" },
            { id: "hired_electrician", label: "Electrician on call", description: "Standard. We'll spec long-life L70 > 50,000 hrs where possible." },
            { id: "service_contract", label: "Service contract", description: "Premium AMC. We can spec adventurous fixtures with shorter life." },
          ]}
        />
      </section>

      <div className="flex justify-between pt-6 border-t border-stone-200">
        <Link href="/studio" className="text-sm text-stone-500 hover:text-stone-700">← Back</Link>
        <Link href="/studio/rooms" className="bg-stone-900 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-stone-800 transition">
          Continue →
        </Link>
      </div>
    </div>
  );
}
