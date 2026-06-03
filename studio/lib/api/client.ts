/**
 * Single-source-of-truth API client for the lighting-engine.
 *
 * Use these typed methods from page components — do NOT call fetch directly.
 * Errors are surfaced as {@link ApiError} which preserves the HTTP status and
 * the parsed FastAPI error envelope (`detail`).
 */

import type {
  BriefRequest,
  ClarificationRequest,
  ConfirmedRoom,
  FurnitureRequest,
  GenerateResponse,
  JobStatus,
  PlanResponse,
  ProjectCreateResponse,
  RoomListResponse,
  WallConfirmation,
  WallsResponse,
} from "./types";

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Polling cadence for `/api/jobs/{job_id}` while a generation is in flight. */
export const JOB_POLL_INTERVAL_MS = 500;

/** Maximum time we'll keep polling before giving up with a timeout error. */
export const JOB_POLL_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  public readonly status: number;
  public readonly detail: unknown;
  constructor(status: number, message: string, detail: unknown = undefined) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface FetchOpts {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: BodyInit;
  headers?: Record<string, string>;
}

async function request<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url, {
    method: opts.method ?? "GET",
    headers: opts.headers,
    body: opts.body,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail: unknown = undefined;
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body && typeof body === "object" && "detail" in body) {
        detail = (body as { detail: unknown }).detail;
        if (typeof detail === "string") {
          message = detail;
        } else {
          message = `${message}: ${JSON.stringify(detail)}`;
        }
      }
    } catch {
      // body wasn't JSON; keep the default message
    }
    throw new ApiError(res.status, message, detail);
  }
  // 204 No Content
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------- projects ----------

export interface CreateProjectArgs {
  ceiling: File;
  furniture?: File | null;
  project_name?: string;
  location?: string;
}

export async function createProject(
  args: CreateProjectArgs,
): Promise<ProjectCreateResponse> {
  const form = new FormData();
  form.append("ceiling", args.ceiling);
  if (args.furniture) form.append("furniture", args.furniture);
  if (args.project_name) form.append("project_name", args.project_name);
  if (args.location) form.append("location", args.location);
  return request<ProjectCreateResponse>("/api/projects", {
    method: "POST",
    body: form,
  });
}

export async function listRooms(projectId: string): Promise<RoomListResponse> {
  return request<RoomListResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms`,
  );
}

// ---------- rooms ----------

export async function getRoom(
  projectId: string,
  roomId: string,
): Promise<ConfirmedRoom> {
  return request<ConfirmedRoom>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}`,
  );
}

export async function postRoomBasics(
  projectId: string,
  roomId: string,
  payload: ClarificationRequest,
): Promise<ConfirmedRoom> {
  return postJson<ConfirmedRoom>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}`,
    payload,
  );
}

export async function getWalls(
  projectId: string,
  roomId: string,
): Promise<WallsResponse> {
  return request<WallsResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}/walls`,
  );
}

export async function postWall(
  projectId: string,
  roomId: string,
  wallIndex: number,
  payload: WallConfirmation,
): Promise<ConfirmedRoom> {
  return postJson<ConfirmedRoom>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}/walls/${wallIndex}`,
    payload,
  );
}

export async function postFurniture(
  projectId: string,
  roomId: string,
  payload: FurnitureRequest,
): Promise<ConfirmedRoom> {
  return postJson<ConfirmedRoom>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}/furniture`,
    payload,
  );
}

export async function postBrief(
  projectId: string,
  roomId: string,
  payload: BriefRequest,
): Promise<ConfirmedRoom> {
  return postJson<ConfirmedRoom>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}/brief`,
    payload,
  );
}

// ---------- generation ----------

export async function generatePlan(
  projectId: string,
  roomId: string,
): Promise<GenerateResponse> {
  return postJson<GenerateResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}/generate`,
    {},
  );
}

export async function getJob(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`);
}

export async function getPlan(
  projectId: string,
  roomId: string,
): Promise<PlanResponse> {
  return request<PlanResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/rooms/${encodeURIComponent(roomId)}/plan`,
  );
}
