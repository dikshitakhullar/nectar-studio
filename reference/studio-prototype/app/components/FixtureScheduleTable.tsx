"use client";

import { Fragment, useState } from "react";
import type { Fixture } from "@/lib/studio/types";

/** Tiny tooltip for inline technical-term explainers.
 * Uses native <details>/<summary> for accessibility — works on hover (focus-within) + click. */
function Explainer({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <span className="relative inline-block group">
      <sup
        className="text-amber-700/70 ml-1 cursor-help select-none"
        aria-label={`What is ${term}?`}
        tabIndex={0}
      >
        ?
      </sup>
      <span
        role="tooltip"
        className="invisible opacity-0 group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100 transition-opacity absolute left-0 top-full mt-1 z-20 w-64 bg-stone-900 text-stone-50 text-[11px] leading-snug rounded-md p-2 shadow-lg normal-case tracking-normal font-normal"
      >
        {children}
      </span>
    </span>
  );
}

function fmtMounting(m: string): string {
  return m.replace(/_/g, " ");
}

function fmtHours(h?: number): string {
  if (!h) return "—";
  if (h >= 1000) return `${(h / 1000).toFixed(0)}k hrs`;
  return `${h} hrs`;
}

function DetailBlock({ label, value, explainer }: { label: string; value: React.ReactNode; explainer?: React.ReactNode }) {
  return (
    <div>
      <div className="text-stone-500 uppercase tracking-wider text-[10px]">
        {label}
        {explainer ? <Explainer term={label}>{explainer}</Explainer> : null}
      </div>
      <div className="text-stone-900 mt-0.5">{value}</div>
    </div>
  );
}

export function FixtureScheduleTable({ fixtures }: { fixtures: Fixture[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (tag: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  };

  return (
    <div className="overflow-x-auto bg-white border border-stone-200 rounded-md">
      <table className="w-full text-xs">
        <thead className="bg-stone-100 text-stone-500 uppercase tracking-wider">
          <tr>
            <th className="p-3 w-6"></th>
            <th className="text-left p-3">Tag</th>
            <th className="text-left p-3">Category</th>
            <th className="text-left p-3">Mounting</th>
            <th className="text-right p-3">Qty</th>
            <th className="text-right p-3">W</th>
            <th className="text-right p-3">CCT</th>
            <th className="text-right p-3">CRI</th>
            <th className="text-right p-3">Beam</th>
            <th className="text-left p-3">Source</th>
          </tr>
        </thead>
        <tbody className="text-stone-700">
          {fixtures.map((f) => {
            const isOpen = expanded.has(f.tag);
            const selectedBrand =
              f.brandPicks && f.selectedBrandIndex !== undefined
                ? f.brandPicks[f.selectedBrandIndex]
                : undefined;
            return (
              <Fragment key={f.tag}>
                <tr
                  className="border-t border-stone-200 hover:bg-stone-50 cursor-pointer"
                  onClick={() => toggle(f.tag)}
                >
                  <td className="p-3 text-stone-400 text-center">
                    <span
                      className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}
                      aria-label={isOpen ? "Collapse row" : "Expand row"}
                    >
                      ▸
                    </span>
                  </td>
                  <td className="p-3 font-medium text-stone-900">{f.tag}</td>
                  <td className="p-3">{f.category}</td>
                  <td className="p-3 text-stone-500">{fmtMounting(f.mounting)}</td>
                  <td className="p-3 text-right">{f.quantity}</td>
                  <td className="p-3 text-right">{f.wattage}</td>
                  <td className="p-3 text-right">{f.cct}K</td>
                  <td className="p-3 text-right">{f.cri ?? "—"}</td>
                  <td className="p-3 text-right">{f.beamAngleDeg ? `${f.beamAngleDeg}°` : "—"}</td>
                  <td className="p-3 text-stone-500">{f.source === "decorative_catalog" ? "Catalog" : "Spec"}</td>
                </tr>
                {isOpen && (
                  <tr className="border-t border-stone-200">
                    <td colSpan={10} className="bg-stone-50 px-4 py-3 text-xs">
                      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                        <DetailBlock label="Tag" value={f.tag} />
                        <DetailBlock label="Category" value={f.category} />
                        <DetailBlock label="Mounting" value={fmtMounting(f.mounting)} />
                        <DetailBlock label="Qty" value={f.quantity} />
                        <DetailBlock label="Wattage" value={`${f.wattage} W`} />
                        <DetailBlock label="Lumens" value={f.lumens ? `${f.lumens} lm` : "—"} />
                        <DetailBlock label="CCT" value={`${f.cct} K`} />
                        <DetailBlock
                          label="CRI"
                          value={
                            f.cri !== undefined
                              ? `${f.cri}${f.r9 !== undefined ? ` (R9: ${f.r9})` : ""}`
                              : "—"
                          }
                          explainer={
                            <>
                              <strong>R9</strong>: saturated red rendering — CRI hides poor R9 (cheap LEDs score CRI 80, R9 &lt; 20). Target &gt; 50, ideal &gt; 80.
                            </>
                          }
                        />
                        {(f.tm30Rf !== undefined || f.tm30Rg !== undefined) && (
                          <DetailBlock
                            label="TM-30 Rf / Rg"
                            value={
                              <>
                                {f.tm30Rf ?? "—"} / {f.tm30Rg ?? "—"}
                              </>
                            }
                            explainer={
                              <>
                                <strong>Rf</strong>: fidelity across 99 colours (like CRI but newer). Target ≥ 85.&nbsp;
                                <strong>Rg</strong>: colour gamut. 100 = neutral, &gt; 100 = enhanced saturation.
                              </>
                            }
                          />
                        )}
                        {f.macAdamSdcm !== undefined && (
                          <DetailBlock
                            label="MacAdam SDCM"
                            value={`${f.macAdamSdcm}-step`}
                            explainer={
                              <>Colour consistency between fixtures. ≤ 3-step means same-batch fixtures look identical.</>
                            }
                          />
                        )}
                        <DetailBlock label="Beam angle" value={f.beamAngleDeg ? `${f.beamAngleDeg}°` : "—"} />
                        <DetailBlock
                          label="Dimmable"
                          value={
                            <>
                              {f.dimmable ? "Yes" : "No"}
                              {f.dimToWarmCapable ? " · Dim-to-warm" : ""}
                            </>
                          }
                        />
                        {f.driverModel && (
                          <DetailBlock label="Driver" value={f.driverModel} />
                        )}
                        {(f.lampLifeL70Hours !== undefined || f.lampLifeL80Hours !== undefined) && (
                          <DetailBlock
                            label="Lamp life L70 / L80"
                            value={`${fmtHours(f.lampLifeL70Hours)} / ${fmtHours(f.lampLifeL80Hours)}`}
                            explainer={
                              <>
                                <strong>L70</strong>: hours until output drops to 70% — LED service life metric.&nbsp;
                                <strong>L80</strong>: same, but at 80% — stricter threshold.
                              </>
                            }
                          />
                        )}
                        {f.source === "architectural_spec" && f.brandPicks && f.brandPicks.length > 0 && (
                          <div className="col-span-2 sm:col-span-3">
                            <div className="text-stone-500 uppercase tracking-wider text-[10px]">
                              Brand picks
                            </div>
                            <div className="text-stone-900 mt-0.5 flex flex-wrap gap-x-3 gap-y-1">
                              {f.brandPicks.map((bp, i) => {
                                const isSelected = f.selectedBrandIndex === i;
                                return (
                                  <span
                                    key={`${bp.tier}-${bp.brand}`}
                                    className={isSelected ? "font-medium text-amber-700" : ""}
                                  >
                                    <span className="text-stone-500 uppercase tracking-wider text-[10px] mr-1">
                                      {bp.tier}
                                    </span>
                                    {bp.brand}
                                    {bp.model ? ` — ${bp.model}` : ""}
                                    {isSelected ? " ✓" : ""}
                                  </span>
                                );
                              })}
                            </div>
                          </div>
                        )}
                        {selectedBrand && (
                          <DetailBlock
                            label="Selected brand"
                            value={`${selectedBrand.brand}${selectedBrand.model ? ` — ${selectedBrand.model}` : ""}`}
                          />
                        )}
                        {f.catalogSku && (
                          <DetailBlock label="Catalog SKU" value={f.catalogSku} />
                        )}
                        {f.applicationNote && (
                          <div className="col-span-2 sm:col-span-3">
                            <div className="text-stone-500 uppercase tracking-wider text-[10px]">
                              Application note
                            </div>
                            <div className="text-stone-900 mt-0.5">{f.applicationNote}</div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
