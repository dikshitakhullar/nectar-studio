/**
 * URL-based state helpers.
 *
 * The studio threads `pid` (project id) and `rid` (room id) through every page
 * via `?pid=…&rid=…`. Centralised here so the param names stay consistent.
 */

import type { ReadonlyURLSearchParams } from "next/navigation";

export interface StudioIds {
  pid: string;
  rid: string | null;
}

/** Build a `?pid=…&rid=…` query string for cross-page navigation. */
export function buildStudioQuery(pid: string, rid?: string | null): string {
  const params = new URLSearchParams();
  params.set("pid", pid);
  if (rid) params.set("rid", rid);
  return params.toString();
}

/** Pull `pid` + `rid` out of the current search params (client side). */
export function readStudioIds(
  searchParams: ReadonlyURLSearchParams | URLSearchParams,
): StudioIds {
  return {
    pid: searchParams.get("pid") ?? "",
    rid: searchParams.get("rid"),
  };
}
