"use client";

import { useState } from "react";

interface Props {
  label: string;
  description?: string;
  selected?: boolean;
  onClick?: () => void;
}

export function AnswerOption({ label, description, selected, onClick }: Props) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left border rounded-md p-4 transition w-full ${
        selected ? "border-amber-700 bg-amber-50" : "border-stone-200 bg-white hover:border-stone-400"
      }`}
    >
      <div className="text-sm font-medium text-stone-900">{label}</div>
      {description && <div className="text-xs text-stone-500 mt-1">{description}</div>}
    </button>
  );
}

// Simple stateful multi-select option group
export function OptionGroup({
  options,
  multi = false,
}: {
  options: { id: string; label: string; description?: string }[];
  multi?: boolean;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const toggle = (id: string) => {
    if (multi) {
      setSelected(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]));
    } else {
      setSelected([id]);
    }
  };
  return (
    <div className="grid sm:grid-cols-2 gap-2">
      {options.map(o => (
        <AnswerOption
          key={o.id}
          label={o.label}
          description={o.description}
          selected={selected.includes(o.id)}
          onClick={() => toggle(o.id)}
        />
      ))}
    </div>
  );
}
