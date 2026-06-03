"use client";

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-stone-500 text-sm">
      <span
        className="inline-block w-4 h-4 border-2 border-stone-300 border-t-amber-700 rounded-full animate-spin"
        aria-hidden
      />
      {label ?? "Loading…"}
    </div>
  );
}

export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-md p-4 space-y-2">
      <div className="text-sm text-red-800 font-medium">Something went wrong</div>
      <div className="text-xs text-red-700 break-words">{message}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs bg-red-700 text-white px-3 py-1.5 rounded-md hover:bg-red-800 transition"
        >
          Retry
        </button>
      )}
    </div>
  );
}

interface Option {
  id: string;
  label: string;
  description?: string;
}

interface OptionGroupProps {
  options: Option[];
  multi?: boolean;
  value: string[];
  onChange: (next: string[]) => void;
}

/** Controlled single-or-multi-select for clarification screens. */
export function OptionGroup({
  options,
  multi = false,
  value,
  onChange,
}: OptionGroupProps) {
  const toggle = (id: string) => {
    if (multi) {
      onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
    } else {
      onChange([id]);
    }
  };
  return (
    <div className="grid sm:grid-cols-2 gap-2">
      {options.map((o) => {
        const selected = value.includes(o.id);
        return (
          <button
            key={o.id}
            type="button"
            onClick={() => toggle(o.id)}
            className={`text-left border rounded-md p-4 transition w-full ${
              selected
                ? "border-amber-700 bg-amber-50"
                : "border-stone-200 bg-white hover:border-stone-400"
            }`}
          >
            <div className="text-sm font-medium text-stone-900">{o.label}</div>
            {o.description && (
              <div className="text-xs text-stone-500 mt-1">{o.description}</div>
            )}
          </button>
        );
      })}
    </div>
  );
}

