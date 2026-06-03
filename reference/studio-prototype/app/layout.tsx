import type { ReactNode } from "react";

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 px-6 py-4 bg-white">
        <div className="text-xs uppercase tracking-[0.2em] text-amber-700/90">Nectar</div>
        <div className="text-lg font-light tracking-tight text-stone-900">Lighting Studio</div>
      </header>
      <main className="px-6 py-8 max-w-3xl mx-auto">{children}</main>
    </div>
  );
}
