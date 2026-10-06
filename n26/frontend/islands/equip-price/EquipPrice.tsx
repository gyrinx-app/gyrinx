import { useLayoutEffect, useRef, useState } from "react";

export type EquipPriceProps = {
    field: string;
    quoted: number;
    label: string;
    min: number;
    max: number;
    id?: string;
    /** What the box already held before React mounted; empty stays empty. */
    initial?: string;
    /** The server-drawn box had focus when the island replaced it. */
    restoreFocus?: boolean;
    selectionStart?: number | null;
    selectionEnd?: number | null;
};

export function EquipPrice({
    field,
    quoted,
    label,
    min,
    max,
    id,
    initial,
    restoreFocus = false,
    selectionStart = null,
    selectionEnd = null,
}: EquipPriceProps) {
    const boxRef = useRef<HTMLInputElement>(null);
    const [raw, setRaw] = useState(initial ?? String(quoted));
    useLayoutEffect(() => {
        const box = boxRef.current;
        if (!restoreFocus || !box) return;
        box.focus();
        if (selectionStart == null || selectionEnd == null) return;
        try {
            box.setSelectionRange(selectionStart, selectionEnd);
        } catch {
            // A number box may refuse a caret range.
        }
    }, [restoreFocus, selectionStart, selectionEnd]);
    const price = Number(raw);
    const delta =
        raw !== "" && Number.isFinite(price) && price !== quoted
            ? `${price > quoted ? "+" : "−"}${Math.abs(price - quoted)}¢`
            : "";

    return (
        <>
            {delta && (
                <span
                    className="shrink-0 text-xs tabular-nums text-muted"
                    title={`Listed at ${quoted}¢`}
                >
                    {delta}
                </span>
            )}
            <input
                ref={boxRef}
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
        </>
    );
}
