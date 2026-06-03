"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useRef } from "react";
import { StepNav } from "../components/StepNav";
import { ErrorBanner, Spinner } from "../components/UIPrimitives";
import { ApiError, createProject } from "@/lib/api/client";
import { buildStudioQuery } from "@/lib/api/url-state";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024; // 10 MB — matches next.config.ts bodySizeLimit

function bytesToHuman(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadPage() {
  const router = useRouter();
  const [ceiling, setCeiling] = useState<File | null>(null);
  const [furniture, setFurniture] = useState<File | null>(null);
  const [projectName, setProjectName] = useState("Delhi pilot");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ceilingRef = useRef<HTMLInputElement>(null);
  const furnitureRef = useRef<HTMLInputElement>(null);

  const sizeError = ceiling && ceiling.size > MAX_UPLOAD_BYTES
    ? `Ceiling file is ${bytesToHuman(ceiling.size)} — max upload is ${bytesToHuman(MAX_UPLOAD_BYTES)}.`
    : null;

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ceiling) {
      setError("Pick a ceiling DWG/DXF before continuing.");
      return;
    }
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await createProject({
        ceiling,
        furniture,
        project_name: projectName || "Untitled project",
      });
      if (result.rooms.length === 0) {
        setError(
          "We couldn't find any rooms in that file — try a different DWG/DXF.",
        );
        setSubmitting(false);
        return;
      }
      // Redirect to /studio/rooms with the new project_id in the URL.
      router.push(`/studio/rooms?${buildStudioQuery(result.project_id)}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`${err.message} (HTTP ${err.status})`);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Upload failed — try again.");
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/upload" />

      <div className="space-y-2">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Upload</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Your project files</h1>
        <p className="text-stone-600 text-sm">
          Drop your ceiling and furniture DWG/DXF. The engine parses the ceiling
          to find rooms; the furniture file is stored for v1.1 but ignored for
          the v1 plan.
        </p>
      </div>

      <form onSubmit={onSubmit} className="space-y-6">
        <label className="block space-y-1">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">Project name</div>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full bg-white border border-stone-200 rounded-md px-3 py-2 text-sm text-stone-900 focus:border-stone-400 outline-none"
            placeholder="Untitled project"
          />
        </label>

        <FilePicker
          inputRef={ceilingRef}
          label="Ceiling plan (RCP)"
          required
          file={ceiling}
          onChange={setCeiling}
          accept=".dwg,.dxf"
          description="The architectural reflected-ceiling plan."
        />

        <FilePicker
          inputRef={furnitureRef}
          label="Furniture layout (optional)"
          required={false}
          file={furniture}
          onChange={setFurniture}
          accept=".dwg,.dxf"
          description="Stored for v1.1 — the v1 parser ignores it."
        />

        {sizeError && <div className="text-xs text-red-700">{sizeError}</div>}
        {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}

        <div className="space-y-2">
          {submitting ? (
            <Spinner label="Parsing your DWG…" />
          ) : (
            <button
              type="submit"
              disabled={!ceiling}
              className="inline-flex items-center gap-2 bg-amber-700 text-white px-5 py-3 rounded-md font-medium hover:bg-amber-800 transition shadow-sm disabled:bg-stone-300 disabled:cursor-not-allowed"
            >
              Continue to rooms →
            </button>
          )}
          <p className="text-xs text-stone-500">
            We&apos;ll list the rooms found in your file on the next screen.
          </p>
        </div>
      </form>

      <div className="border-t border-stone-200 pt-6">
        <Link href="/studio" className="text-sm text-stone-500 hover:text-stone-700">
          ← Back to start
        </Link>
      </div>
    </div>
  );
}

interface FilePickerProps {
  label: string;
  required: boolean;
  file: File | null;
  onChange: (next: File | null) => void;
  accept: string;
  description: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
}

function FilePicker({
  label,
  required,
  file,
  onChange,
  accept,
  description,
  inputRef,
}: FilePickerProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <div className="text-xs uppercase tracking-wider text-amber-700/90">
          {label}
          {required && <span className="text-red-700 ml-1">*</span>}
        </div>
        {file && (
          <button
            type="button"
            onClick={() => {
              onChange(null);
              if (inputRef.current) inputRef.current.value = "";
            }}
            className="text-xs text-stone-500 hover:text-stone-700"
          >
            Clear
          </button>
        )}
      </div>
      <label className="block">
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          required={required}
          onChange={(e) => onChange(e.target.files?.[0] ?? null)}
          className="block w-full text-sm text-stone-700 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-stone-100 file:text-stone-700 hover:file:bg-stone-200 file:cursor-pointer cursor-pointer"
        />
      </label>
      <p className="text-xs text-stone-500">{description}</p>
      {file && (
        <div className="text-xs text-stone-600">
          Selected: <span className="text-stone-900 font-medium">{file.name}</span>{" "}
          <span className="text-stone-400">({bytesToHuman(file.size)})</span>
        </div>
      )}
    </div>
  );
}
