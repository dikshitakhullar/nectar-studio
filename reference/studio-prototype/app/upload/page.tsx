"use client";

import Link from "next/link";
import { useState } from "react";
import { StepNav } from "../components/StepNav";

const FILE_TYPES = [
  "Ceiling plan (RCP)",
  "Floor plan",
  "Furniture layout",
  "Electrical plan",
  "HVAC drawings",
  "3D renders / photos",
  "Other",
];

const SAMPLE_FILES = [
  "sharma-rcp.pdf",
  "sharma-floor-plan.pdf",
  "living-room-furniture-layout.png",
  "electrical-layout.pdf",
  "hvac-drawing.pdf",
  "3d-render-evening.png",
  "moodboard.pdf",
];

function guessType(filename: string): string {
  const lower = filename.toLowerCase();
  if (lower.includes("rcp") || lower.includes("ceiling")) return "Ceiling plan (RCP)";
  if (lower.includes("floor")) return "Floor plan";
  if (lower.includes("furniture") || lower.includes("sketchup")) return "Furniture layout";
  if (lower.includes("electrical")) return "Electrical plan";
  if (lower.includes("hvac")) return "HVAC drawings";
  if (
    lower.includes("3d") ||
    lower.includes("render") ||
    lower.includes("photo") ||
    lower.includes("moodboard")
  )
    return "3D renders / photos";
  return "Other";
}

function fileIcon(type: string): string {
  if (type === "3D renders / photos") return "🖼";
  return "📄";
}

interface UploadedFile {
  id: string;
  filename: string;
  type: string;
}

export default function UploadPage() {
  const [files, setFiles] = useState<UploadedFile[]>([]);

  const addSampleFile = () => {
    const idx = files.length % SAMPLE_FILES.length;
    const filename = SAMPLE_FILES[idx];
    setFiles((f) => [
      ...f,
      {
        id: `${Date.now()}-${idx}`,
        filename,
        type: guessType(filename),
      },
    ]);
  };

  const updateType = (id: string, type: string) => {
    setFiles((f) => f.map((file) => (file.id === id ? { ...file, type } : file)));
  };

  const removeFile = (id: string) => {
    setFiles((f) => f.filter((file) => file.id !== id));
  };

  const has3DRenders = files.some((f) => f.type === "3D renders / photos");

  return (
    <div className="space-y-8">
      <StepNav currentHref="/studio/upload" />

      <div className="space-y-2">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Upload</div>
        <h1 className="text-2xl font-light tracking-tight text-stone-900">Your project files</h1>
        <p className="text-stone-600 text-sm">Drop what you have — RCP, furniture layout, 3D renders, whatever&apos;s drawn already. We layer lighting on top, we don&apos;t redraw your plan.</p>
      </div>

      {/* Drop zone */}
      <button
        type="button"
        onClick={addSampleFile}
        className="w-full border-2 border-dashed border-stone-300 rounded-lg p-12 text-center hover:border-amber-700 hover:bg-amber-50 transition cursor-pointer block"
      >
        <div className="text-3xl text-stone-400 mb-2">⬆</div>
        <div className="text-sm font-medium text-stone-900">Drop files here or click to browse</div>
        <div className="text-xs text-stone-500 mt-1">PDFs, images, SketchUp screenshots, photos</div>
        <div className="text-xs text-stone-400 mt-3">(Prototype: clicking adds a sample file)</div>
      </button>

      {/* Uploaded files list */}
      {files.length > 0 ? (
        <section className="space-y-2">
          <div className="text-xs uppercase tracking-wider text-amber-700/90">
            Uploaded files ({files.length})
          </div>
          <div className="space-y-2">
            {files.map((file) => (
              <div
                key={file.id}
                className="bg-white border border-stone-200 rounded-md px-4 py-3 flex items-center gap-3"
              >
                <div className="text-xl">{fileIcon(file.type)}</div>
                <div className="flex-1 text-sm text-stone-900 truncate">{file.filename}</div>
                <select
                  value={file.type}
                  onChange={(e) => updateType(file.id, e.target.value)}
                  className="bg-stone-100 border border-stone-200 rounded-md px-2 py-1 text-xs text-stone-700"
                >
                  {FILE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => removeFile(file.id)}
                  className="text-stone-400 hover:text-stone-700 text-lg leading-none"
                  aria-label="Remove file"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <p className="text-sm text-stone-500">No files yet. Add one above to get started.</p>
      )}

      {/* 3D renders shortcut callout */}
      {has3DRenders && (
        <div className="bg-amber-50 border border-amber-200 rounded-md p-5">
          <div className="flex items-start gap-3">
            <div className="text-amber-700 text-xl leading-none">✨</div>
            <div className="space-y-1 flex-1">
              <div className="text-sm font-medium text-stone-900">3D renders detected.</div>
              <p className="text-xs text-stone-600">
                You can skip wall-by-wall verification — we&apos;ll work directly from your visuals.
              </p>
              <Link
                href="/studio/project-profile"
                className="inline-flex items-center gap-2 border border-stone-300 text-stone-700 px-4 py-2 rounded-md text-sm hover:border-stone-500 transition mt-2 bg-white"
              >
                Skip wall verification →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Primary CTA */}
      <div className="space-y-2">
        <Link
          href="/studio/project-profile"
          className="inline-flex items-center gap-2 bg-amber-700 text-white px-5 py-3 rounded-md font-medium hover:bg-amber-800 transition shadow-sm"
        >
          Continue to project profile →
        </Link>
        <p className="text-xs text-stone-500">
          We&apos;ll walk through your inputs and confirm room details.
        </p>
      </div>

      <div className="border-t border-stone-200 pt-6">
        <Link href="/studio" className="text-sm text-stone-500 hover:text-stone-700">
          ← Back to start
        </Link>
      </div>
    </div>
  );
}
