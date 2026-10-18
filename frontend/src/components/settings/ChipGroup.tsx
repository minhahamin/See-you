interface Option<T> {
  value: T;
  label: string;
}

interface Props<T extends string | number> {
  label: string;
  description?: string;
  options: Option<T>[];
  selected: T[];
  onToggle: (value: T) => void;
}

/** 칩 형태의 선택 그룹. 단일/다중 선택 여부는 onToggle을 처리하는 쪽이 정한다. */
export default function ChipGroup<T extends string | number>({
  label,
  description,
  options,
  selected,
  onToggle,
}: Props<T>) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold">{label}</legend>
      {description && <p className="mt-0.5 text-xs text-text-sub">{description}</p>}
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((o) => {
          const on = selected.includes(o.value);
          return (
            <button
              key={String(o.value)}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(o.value)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition-colors ${
                on ? 'bg-primary text-white shadow-soft' : 'bg-bg text-text-main/70 hover:text-text-main'
              }`}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
