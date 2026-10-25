import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { iconProps } from "@/components/shared/icon";
import { cn } from "@/lib/utils";

// Adapted from 21st.dev "Choicebox" (id 34718). One native radio per card, so arrow keys, focus and form semantics come
// from the browser. The card's label selects; "What we'll check" sits outside the label, so opening it never selects.
// Hairline borders, the selected card in the accent tint with an accent edge. No motion.

export interface PickerOption<T extends string> {
  id: T;
  /** Small line above the title, e.g. "Classic". */
  kicker: string;
  title: string;
  description: string;
  checks: string[];
}

export function AttackCardPicker<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: PickerOption<T>[];
  value: T | null;
  onChange: (id: T) => void;
  label: string;
}) {
  const name = useId();
  return (
    <fieldset>
      <legend className="sr-only">{label}</legend>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {options.map((opt) => (
          <Card key={opt.id} option={opt} name={name} selected={value === opt.id} onSelect={() => onChange(opt.id)} />
        ))}
      </div>
    </fieldset>
  );
}

function Card<T extends string>({ option, name, selected, onSelect }: { option: PickerOption<T>; name: string; selected: boolean; onSelect: () => void }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border transition-colors",
        selected ? "border-accent bg-accent-tint shadow-[inset_0_0_0_1px_var(--accent)]" : "border-rule-strong bg-surface hover:border-ink-faint",
      )}
    >
      <label className="flex flex-1 cursor-pointer gap-3 p-4">
        <input
          type="radio"
          name={name}
          value={option.id}
          checked={selected}
          onChange={onSelect}
          className="peer sr-only"
        />
        <span
          aria-hidden
          className={cn(
            // Round: the one circle in the app, because a circle is what says "pick one" (a square reads as a checkbox).
            "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent",
            selected ? "border-accent" : "border-ink-muted",
          )}
        >
          {selected && <span className="size-2 rounded-full bg-accent" />}
        </span>
        <span className="min-w-0">
          <span className="block text-xs font-medium text-ink-muted">{option.kicker}</span>
          <span className="block font-semibold">{option.title}</span>
          <span className="mt-1 block text-sm text-ink-muted">{option.description}</span>
        </span>
      </label>
      <div className="border-t border-rule px-4 py-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen((o) => !o)}
          className="touch-target flex items-center gap-1 text-sm text-ink-muted transition-colors hover:text-ink"
        >
          <ChevronDown {...iconProps} className={cn("transition-transform", open && "rotate-180")} />
          What we'll check
        </button>
        {open && (
          <ul id={listId} className="mt-1.5 mb-1 space-y-1 pl-5 text-sm">
            {option.checks.map((c) => (
              <li key={c} className="list-disc marker:text-ink-faint">
                {c}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
