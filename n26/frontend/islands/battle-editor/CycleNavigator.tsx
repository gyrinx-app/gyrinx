import { useEffect, useState } from "react";
import { Badge, Button, FieldErrors, Icon } from "../../ui";

export type CycleChoice = {
    value: Record<string, string | number>;
    order: number;
    name: string;
    phase: string;
    label: string;
    startsOn: string | null;
    endsOn: string | null;
    hint: string;
    isCurrent: boolean;
};
export type CycleOptions = {
    configured: boolean;
    current: string;
    currentValue: CycleChoice["value"] | null;
    lastOrder: number;
    choices: CycleChoice[];
    previous: number | null;
    next: number | null;
};
const key = (choice: CycleChoice) => JSON.stringify(choice.value);
const dateLabel = (value: string) =>
    new Intl.DateTimeFormat("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
    }).format(new Date(`${value}T00:00:00Z`));

async function read(
    href: string,
    value: string,
    signal?: AbortSignal,
): Promise<CycleOptions> {
    const response = await fetch(
        `${href}?${new URLSearchParams({ selected: value })}`,
        {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
            signal,
        },
    );
    if (
        !response.ok ||
        !response.headers.get("content-type")?.includes("application/json")
    )
        throw new Error();
    const data = await response.json();
    if (
        !data ||
        !Array.isArray(data.choices) ||
        typeof data.current !== "string"
    )
        throw new Error();
    return data;
}

export function CycleNavigator({
    initial,
    value,
    onChange,
    readUrl,
    errors = [],
    onBusyChange,
}: {
    initial: CycleOptions;
    value: string;
    onChange: (value: string) => void;
    readUrl: string;
    errors?: string[];
    onBusyChange?: (busy: boolean) => void;
}) {
    const [options, setOptions] = useState(initial);
    const [moving, setMoving] = useState<number | null>(null);
    const [error, setError] = useState("");
    const selected = options.choices.find((choice) => key(choice) === value);
    const unassigned = !value || value === "null";
    useEffect(() => {
        onBusyChange?.(moving !== null);
        return () => onBusyChange?.(false);
    }, [moving, onBusyChange]);
    useEffect(() => {
        if (
            unassigned ||
            options.choices.some((choice) => key(choice) === value)
        )
            return;
        const controller = new AbortController();
        setError("");
        void read(readUrl, value, controller.signal)
            .then((data) => {
                if (!controller.signal.aborted) setOptions(data);
            })
            .catch(() => {
                if (!controller.signal.aborted)
                    setError("The cycle could not be loaded. Try again.");
            });
        return () => controller.abort();
    }, [readUrl, value]);

    async function move(direction: number) {
        if (!selected || moving !== null) return;
        const order = selected.order + direction;
        const available = options.choices.find(
            (choice) => choice.order === order,
        );
        if (available) {
            onChange(key(available));
            return;
        }
        setMoving(direction);
        setError("");
        try {
            const updated = await read(readUrl, value);
            const next = updated.choices.find(
                (choice) => choice.order === order,
            );
            if (!next) throw new Error();
            setOptions(updated);
            onChange(key(next));
        } catch {
            setError("The cycle could not be loaded. Try again.");
        } finally {
            setMoving(null);
        }
    }
    return (
        <fieldset className="space-y-2" aria-label="Campaign cycle">
            <legend className="mb-2 font-medium">Campaign cycle</legend>
            <div className="flex h-48 flex-col gap-2">
                <div className="flex min-h-0 flex-1 items-center gap-3">
                    <Button
                        size="sm"
                        variant="ghost"
                        aria-label="Previous cycle"
                        className="min-h-11 shrink-0"
                        busy={moving === -1}
                        disabled={
                            !selected || selected.order <= 1 || moving !== null
                        }
                        onClick={() => void move(-1)}
                    >
                        <Icon
                            name="chevron-right"
                            className="size-4 rotate-180"
                        />
                    </Button>
                    <div
                        className={`h-full min-w-0 flex-1 overflow-y-auto rounded-control border p-2 text-center ${selected?.isCurrent ? "border-accent bg-accent/5" : "border-box-border"}`}
                        aria-live="polite"
                        aria-atomic="true"
                    >
                        <div className="mb-1 h-6">
                            {selected?.isCurrent && (
                                <Badge>Current cycle</Badge>
                            )}
                        </div>
                        <p className="text-lg font-semibold">
                            {selected?.name ??
                                (unassigned
                                    ? "No cycle selected"
                                    : "Selected cycle")}
                        </p>
                        {selected && (
                            <p className="text-sm text-muted">
                                {selected.phase}
                            </p>
                        )}
                        {selected && (
                            <p className="mt-1 text-sm">
                                {selected.startsOn &&
                                    !selected.endsOn &&
                                    "From "}
                                {!selected.startsOn &&
                                    selected.endsOn &&
                                    "Until "}
                                {selected.startsOn && (
                                    <time dateTime={selected.startsOn}>
                                        {dateLabel(selected.startsOn)}
                                    </time>
                                )}
                                {selected.startsOn && selected.endsOn && " – "}
                                {selected.endsOn && (
                                    <time dateTime={selected.endsOn}>
                                        {dateLabel(selected.endsOn)}
                                    </time>
                                )}
                                {!selected.startsOn &&
                                    !selected.endsOn &&
                                    "Dates not set"}
                            </p>
                        )}
                    </div>
                    <Button
                        size="sm"
                        variant="ghost"
                        aria-label="Next cycle"
                        className="min-h-11 shrink-0"
                        busy={moving === 1}
                        disabled={
                            !selected ||
                            selected.order >= options.lastOrder ||
                            moving !== null
                        }
                        onClick={() => void move(1)}
                    >
                        <Icon name="chevron-right" />
                    </Button>
                </div>
                <div className="grid h-11 shrink-0 grid-cols-2 items-center gap-2">
                    <div className="min-w-0">
                        {!selected?.isCurrent && options.currentValue && (
                            <Button
                                size="sm"
                                variant="default"
                                disabled={moving !== null}
                                className="h-11 w-full whitespace-normal leading-tight"
                                onClick={() =>
                                    onChange(
                                        JSON.stringify(options.currentValue),
                                    )
                                }
                            >
                                Return to current cycle
                            </Button>
                        )}
                    </div>
                    <div className="min-w-0">
                        {!unassigned && (
                            <Button
                                size="sm"
                                variant="ghost"
                                disabled={moving !== null}
                                className="h-11 w-full whitespace-normal leading-tight"
                                onClick={() => onChange("null")}
                            >
                                Leave unassigned
                            </Button>
                        )}
                    </div>
                </div>
            </div>
            <div
                className="h-16 overflow-y-auto space-y-1 text-sm"
                aria-live="polite"
            >
                <FieldErrors errors={errors} />
                {selected?.hint && <p>{selected.hint}</p>}
                {error && <p role="alert">{error}</p>}
            </div>
        </fieldset>
    );
}
