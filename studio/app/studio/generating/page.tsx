"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import {
  ApiError,
  JOB_POLL_INTERVAL_MS,
  JOB_POLL_TIMEOUT_MS,
  generatePlan,
  getJob,
} from "@/lib/api/client";
import { buildStudioQuery, readStudioIds } from "@/lib/api/url-state";

interface MissingFieldsDetail {
  missing_fields?: string[];
}

export default function GeneratingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { pid, rid } = readStudioIds(searchParams);

  const [status, setStatus] = useState<string>("starting");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [missingFields, setMissingFields] = useState<string[] | null>(null);
  // Guard against double-starts in dev (React strict mode) and re-renders.
  const startedRef = useRef(false);

  const startGeneration = useCallback(async () => {
    if (!pid || !rid) {
      setError("Missing project or room id.");
      return;
    }
    setError(null);
    setMissingFields(null);
    setStatus("starting");

    const pollJob = async (jobId: string): Promise<void> => {
      const started = Date.now();
      while (true) {
        if (Date.now() - started > JOB_POLL_TIMEOUT_MS) {
          setError(
            `Generation timed out after ${Math.round(JOB_POLL_TIMEOUT_MS / 1000)}s.`,
          );
          return;
        }
        let job;
        try {
          job = await getJob(jobId);
        } catch (err) {
          if (err instanceof ApiError) {
            setError(`${err.message} (HTTP ${err.status})`);
          } else if (err instanceof Error) {
            setError(err.message);
          } else {
            setError("Polling failed.");
          }
          return;
        }
        setStatus(job.status);
        setElapsedMs(Date.now() - started);
        if (job.status === "done") {
          router.push(`/studio/pack?${buildStudioQuery(pid, rid)}`);
          return;
        }
        if (job.status === "failed") {
          setError(job.error ?? "The engine reported a failed job.");
          return;
        }
        await new Promise((res) => setTimeout(res, JOB_POLL_INTERVAL_MS));
      }
    };

    try {
      const { job_id } = await generatePlan(pid, rid);
      setStatus("pending");
      await pollJob(job_id);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 400 && err.detail && typeof err.detail === "object") {
          const detail = err.detail as MissingFieldsDetail;
          if (Array.isArray(detail.missing_fields)) {
            setMissingFields(detail.missing_fields);
            setError(
              `Missing required fields before we can generate: ${detail.missing_fields.join(", ")}`,
            );
            return;
          }
        }
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Generation failed — please retry.");
      }
    }
  }, [pid, rid, router]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void startGeneration();
  }, [startGeneration]);

  if (!pid || !rid) {
    return (
      <div className="space-y-6">
        <StepNav currentHref="/studio/generating" />
        <ErrorBanner message="Missing project or room id. Start from upload." />
      </div>
    );
  }

  const retry = () => {
    startedRef.current = false;
    void startGeneration();
  };

  return (
    <div className="space-y-10 py-12 min-h-[60vh] flex flex-col justify-center max-w-md mx-auto">
      <StepNav currentHref="/studio/generating" query={buildStudioQuery(pid, rid)} />

      <div className="space-y-3 text-center">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Studio at work</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">
          Designing your room…
        </h1>
        <p className="text-stone-500 text-sm">
          Status: <span className="text-stone-900 font-medium">{status}</span>
          {elapsedMs > 0 && (
            <span className="text-stone-400"> · {(elapsedMs / 1000).toFixed(1)}s</span>
          )}
        </p>
      </div>

      {!error && <Spinner label="Generating plan… this can take 5–30 seconds." />}

      {error && (
        <div className="space-y-3">
          <ErrorBanner message={error} />
          {missingFields && missingFields.length > 0 ? (
            <Link
              href={`/studio/room-basics?${buildStudioQuery(pid, rid)}`}
              className="inline-block bg-amber-700 text-white px-5 py-2 rounded-md text-sm hover:bg-amber-800 transition"
            >
              ← Fix room basics
            </Link>
          ) : (
            <button
              type="button"
              onClick={retry}
              className="inline-block bg-amber-700 text-white px-5 py-2 rounded-md text-sm hover:bg-amber-800 transition"
            >
              Retry generation
            </button>
          )}
        </div>
      )}
    </div>
  );
}
