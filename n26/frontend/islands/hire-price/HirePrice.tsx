import { useState } from "react";

export type HirePriceProps = {
    field: string;
    quoted: number;
    label: string;
    min: number;
    max: number;
    id: string;
    /** What the box already held before React mounted; empty stays empty. */
    initial?: string;
};

export function HirePrice({
    field,
    quoted,
    label,
    min,
    max,
    id,
    initial,
}: HirePriceProps) {
    const [raw, setRaw] = useState(initial ?? String(quoted));
    const price = Number(raw);
    const delta =
        raw !== "" && Number.isFinite(price) && price !== quoted
            ? `${price > quoted ? "+" : "−"}${Math.abs(price - quoted)}¢`
            : "";

    return (
        <span className="flex items-center justify-end gap-1.5">
            <input
                id={id || undefined}
                type="number"
                name={field}
                value={raw}
                min={min}
                max={max}
                step={1}
                inputMode="numeric"
                aria-label={`Price for ${label}`}
                className="w-16 shrink-0 rounded-control border border-box-border bg-[var(--color-input-bg)] px-1.5 py-1 text-right text-sm tabular-nums text-ink-900 shadow-[var(--shadow-input)] focus-ring dark:text-ink-100"
                onChange={(event) => setRaw(event.target.value)}
            />
            {delta && (
                <span
                    className="shrink-0 text-xs tabular-nums text-muted"
                    title={`Listed at ${quoted}¢`}
                >
                    ({delta})
                </span>
            )}
        </span>
    );
}
