import { useLayoutEffect, useRef, useState } from "react";
import { Button } from "../../ui";
import {
    OptionChoices,
    type PickGroup,
    type FocusedChoice,
    type ResolutionGroup,
    resolveOptions,
    useChoices,
} from "./OptionChoices";

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
    choices?: PickGroup[];
    initialSelections?: Record<string, string[]>;
    focusedChoice?: FocusedChoice;
    purchase?: {
        name: string;
        repeat: boolean;
        tradePoints: number | null;
        exclusive: boolean;
        buy: { label: string; target: string };
    };
};

export type OptionChangeProps = {
    changing: true;
    choices: PickGroup[];
    before: number;
    held: string[];
    resolution: ResolutionGroup[];
    initialSelections?: Record<string, string[]>;
    focusedChoice?: FocusedChoice;
};

export function EquipPrice(props: EquipPriceProps | OptionChangeProps) {
    if ("changing" in props) return <OptionChange {...props} />;
    if (props.purchase) return <Purchase {...props} />;
    return <PriceBox {...props} />;
}

function PriceBox({
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
    purchase,
    onPriceChange,
}: EquipPriceProps & { onPriceChange?: (raw: string) => void }) {
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
                aria-label={`${purchase ? "Base price" : "Price"} for ${label}`}
                className="w-16 shrink-0 rounded-control border border-box-border bg-[var(--color-input-bg)] px-1.5 py-1 text-right text-sm tabular-nums text-ink-900 shadow-[var(--shadow-input)] focus-ring dark:text-ink-100"
                onChange={(event) => {
                    setRaw(event.target.value);
                    onPriceChange?.(event.target.value);
                }}
            />
        </>
    );
}

function Purchase(props: EquipPriceProps) {
    const purchase = props.purchase!;
    const [raw, setRaw] = useState(props.initial ?? String(props.quoted));
    const choices = useChoices(props.choices ?? [], props.initialSelections);
    const amount = raw === "" ? props.quoted : Number(raw);
    const total = Number.isFinite(amount) ? amount + choices.surcharge : null;
    return (
        <>
            <div className="flex min-h-9 items-center gap-2">
                {purchase.repeat ? (
                    <span className="min-w-0 flex-1 text-sm text-muted">
                        Buy another
                    </span>
                ) : (
                    <>
                        <span className="flex min-w-0 flex-1 items-center gap-2 text-sm text-ink-900 dark:text-ink-100">
                            <span className="n26-cp-rail" aria-hidden="true" />
                            <span className="min-w-0 font-semibold sm:truncate">
                                {purchase.name}
                            </span>
                        </span>
                        {purchase.exclusive ? (
                            <span
                                className="shrink-0 text-xs font-semibold tabular-nums text-ink-900 dark:text-ink-100"
                                title="Exclusive — equipment list only"
                            >
                                E
                            </span>
                        ) : purchase.tradePoints ? (
                            <span
                                className="shrink-0 text-xs tabular-nums text-ink-900 dark:text-ink-100"
                                title={`${purchase.tradePoints} trade points`}
                            >
                                {purchase.tradePoints}TP
                            </span>
                        ) : null}
                    </>
                )}
                <div className="n26-cp-price flex shrink-0 items-center justify-end gap-1.5 text-sm text-ink-900 dark:text-ink-100">
                    <PriceBox {...props} onPriceChange={setRaw} />
                </div>
                <span className="flex shrink-0 items-center gap-1">
                    <Button
                        size="sm"
                        variant="success"
                        type="submit"
                        name="thing"
                        value={purchase.buy.target}
                    >
                        {purchase.buy.label}
                    </Button>
                </span>
            </div>
            <div className={purchase.repeat ? "" : "n26-cp-inset"}>
                <OptionChoices
                    groups={props.choices ?? []}
                    {...choices}
                    focusedChoice={props.focusedChoice}
                />
                <p
                    role="status"
                    className="py-1 text-right text-sm font-semibold tabular-nums text-ink-900 dark:text-ink-100"
                >
                    {total === null
                        ? "Enter a valid base price."
                        : `Total ${total}¢`}
                </p>
            </div>
        </>
    );
}

function OptionChange(props: OptionChangeProps) {
    const choices = useChoices(props.choices, props.initialSelections);
    const resolved = resolveOptions(
        props.resolution,
        choices.picked.map((option) => option.setKey),
    );
    const setKeys = new Set(resolved?.map((option) => option.setKey));
    const unchanged =
        setKeys.size === props.held.length &&
        props.held.every((key) => setKeys.has(key));
    const difference =
        resolved === null
            ? null
            : unchanged
              ? 0
              : resolved.reduce((sum, option) => sum + option.price, 0) -
                props.before;
    return (
        <>
            <OptionChoices
                groups={props.choices}
                {...choices}
                focusedChoice={props.focusedChoice}
            />
            <p
                role="status"
                className="pt-2 text-sm font-semibold tabular-nums text-ink-900 dark:text-ink-100"
            >
                {difference === null
                    ? "Price preview unavailable."
                    : difference > 0
                      ? `Options charge ${difference}¢`
                      : difference < 0
                        ? `Options refund ${-difference}¢`
                        : "No price change"}
            </p>
        </>
    );
}
