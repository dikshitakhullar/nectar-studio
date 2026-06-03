import Link from "next/link";

export default function StudioLandingPage() {
  return (
    <div className="space-y-8">
      <div className="space-y-3">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Prototype</div>
        <h1 className="text-3xl font-light tracking-tight text-stone-900 leading-tight">
          Upload, confirm, generate.
        </h1>
        <p className="text-stone-600 leading-relaxed">
          Drop an architectural DWG/DXF, pick a room, walk through a short
          clarification, and get a lighting plan back from the engine in
          seconds.
        </p>
      </div>
      <Link
        href="/studio/upload"
        className="inline-flex items-center gap-2 bg-amber-700 text-white px-5 py-3 rounded-md font-medium hover:bg-amber-800 transition shadow-sm"
      >
        Start a project →
      </Link>
    </div>
  );
}
