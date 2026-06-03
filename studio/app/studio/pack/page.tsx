"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import { FixtureScheduleTable } from "../components/FixtureScheduleTable";
import { ApiError, getPlan } from "@/lib/api/client";
import type { PlanResponse } from "@/lib/api/types";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

function formatLux(value: number): string {
  return `${value.toFixed(0)} lx`;
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

export default function PackPage() {
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id.");
      return;
    }
    setError(null);
    try {
      const result = await getPlan(pid, rid);
      setPlan(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to load the plan.");
      }
    }
  }, [pid, rid]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!pid || !rid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/pack" />
        <ErrorBanner message="Missing project or room id. Start from upload." />
      </div>
    );
  }

  if (!plan && !error) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/pack" query={buildStudioQuery(pid, rid)} />
        <Spinner label="Loading plan…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/pack" query={buildStudioQuery(pid, rid)} />
        <ErrorBanner message={error} onRetry={load} />
      </div>
    );
  }

  if (!plan) return null;

  const totalFixtures = plan.fixture_schedule.reduce((sum, row) => sum + row.count, 0);

  return (
    <div className="space-y-12 max-w-4xl mx-auto">
      <StepNav currentHref="/studio/pack" query={buildStudioQuery(pid, rid)} />

      <header className="space-y-3 border-b border-stone-200 pb-8">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Lighting Plan</div>
        <h1 className="text-3xl font-light tracking-tight text-stone-900">
          Plan for room {plan.room_id}
        </h1>
        <div className="flex gap-6 text-sm text-stone-600 pt-2 flex-wrap">
          <div>
            <span className="text-stone-400">Fixtures</span>{" "}
            <span className="text-stone-900">{totalFixtures}</span>
          </div>
          <div>
            <span className="text-stone-400">Schedule rows</span>{" "}
            <span className="text-stone-900">{plan.fixture_schedule.length}</span>
          </div>
          <div>
            <span className="text-stone-400">Mean lux</span>{" "}
            <span className="text-stone-900">{formatLux(plan.lux_uniformity.mean_lux)}</span>
          </div>
          <div>
            <span className="text-stone-400">Uniformity</span>{" "}
            <span className="text-stone-900">{formatPercent(plan.lux_uniformity.uniformity)}</span>
          </div>
        </div>
      </header>

      {plan.warnings.length > 0 && (
        <section className="space-y-2 bg-amber-50 border border-amber-200 rounded-md p-4">
          <div className="text-xs uppercase tracking-wider text-amber-700">Warnings</div>
          <ul className="text-sm text-stone-700 list-disc pl-5 space-y-1">
            {plan.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Design intent</div>
        <div className="text-stone-700 whitespace-pre-line text-sm leading-relaxed">
          {plan.design_rationale || (
            <span className="text-stone-400 italic">
              The engine did not return a rationale.
            </span>
          )}
        </div>
      </section>

      {plan.design_notes.length > 0 && (
        <section className="space-y-4">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Design notes</div>
          <ul className="text-sm text-stone-700 list-disc pl-5 space-y-1">
            {plan.design_notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Reflected ceiling plan</div>
        {plan.rcp_svg ? (
          <div
            className="rcp-container bg-white border border-stone-200 rounded-md p-4"
            // The engine is trusted: SVG is server-generated, no user content.
            dangerouslySetInnerHTML={{ __html: plan.rcp_svg }}
          />
        ) : (
          <div className="bg-white border border-stone-200 rounded-md p-6 text-sm text-stone-500">
            No RCP SVG returned by the engine.
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Furniture plan</div>
        {plan.furniture_svg ? (
          <div
            className="furniture-container bg-white border border-stone-200 rounded-md p-4"
            dangerouslySetInnerHTML={{ __html: plan.furniture_svg }}
          />
        ) : (
          <div className="bg-white border border-stone-200 rounded-md p-6 text-sm text-stone-500">
            No furniture SVG returned by the engine.
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Lux uniformity</div>
        <div className="bg-white border border-stone-200 rounded-md p-4 grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <Stat label="Mean" value={formatLux(plan.lux_uniformity.mean_lux)} />
          <Stat label="Min" value={formatLux(plan.lux_uniformity.min_lux)} />
          <Stat label="Max" value={formatLux(plan.lux_uniformity.max_lux)} />
          <Stat label="Uniformity" value={formatPercent(plan.lux_uniformity.uniformity)} />
          <Stat label="Target" value={formatLux(plan.lux_uniformity.target_lux)} />
          <Stat
            label="Meets target"
            value={plan.lux_uniformity.meets_target ? "Yes" : "No"}
            tone={plan.lux_uniformity.meets_target ? "good" : "warn"}
          />
        </div>
      </section>

      <section className="space-y-4">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">Fixture schedule</div>
        <FixtureScheduleTable rows={plan.fixture_schedule} />
      </section>

      <div className="border-t border-stone-200 pt-6 flex justify-between">
        <Link
          href={`/studio/brief?${buildStudioQuery(pid, rid)}`}
          className="text-sm text-stone-500 hover:text-stone-700"
        >
          ← Back to brief
        </Link>
        <Link
          href={`/studio/generating?${buildStudioQuery(pid, rid)}`}
          className="text-sm text-amber-700 hover:text-amber-800"
        >
          Regenerate
        </Link>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "warn";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-700"
      : tone === "warn"
        ? "text-amber-700"
        : "text-stone-900";
  return (
    <div>
      <div className="text-stone-500 uppercase tracking-wider text-[10px]">{label}</div>
      <div className={`${toneClass} mt-0.5 text-sm font-medium`}>{value}</div>
    </div>
  );
}
