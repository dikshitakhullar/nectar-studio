import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-stone-50 text-stone-900 px-6 py-16">
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="space-y-3">
          <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Nectar</div>
          <h1 className="text-4xl font-light tracking-tight">Lighting Studio</h1>
          <p className="text-stone-600 leading-relaxed">
            Upload an architectural DWG/DXF. Confirm the room. Get a generated
            lighting plan, fixture schedule, and rationale — backed by the
            nectar-studio lighting engine.
          </p>
        </div>
        <Link
          href="/studio/upload"
          className="inline-flex items-center gap-2 bg-amber-700 text-white px-5 py-3 rounded-md font-medium hover:bg-amber-800 transition shadow-sm"
        >
          Start a project →
        </Link>
      </div>
    </main>
  );
}
