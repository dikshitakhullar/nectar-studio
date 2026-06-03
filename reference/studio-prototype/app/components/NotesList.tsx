export function NotesList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="space-y-3">
      <div className="text-xs uppercase tracking-wider text-amber-700/90">{title}</div>
      <ul className="space-y-2 text-sm text-stone-700">
        {items.map((note, i) => (
          <li key={i} className="border-l-2 border-amber-700/40 pl-3 leading-relaxed">
            {note}
          </li>
        ))}
      </ul>
    </section>
  );
}
