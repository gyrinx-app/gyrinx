import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Callout, Field, Input, RadioCard, RadioCards } from "../../ui";

type RollField = {
    label: string;
    helpText: string;
    value: string;
    errors: string[];
};

export type PoolRollProps = {
    count: RollField;
    rolled: RollField;
    table: string;
    tableErrors: string[];
    tables: {
        value: string;
        label: string;
        die: string;
        lowest: number;
        highest: number;
    }[];
    previewUrl: string;
    assetType: string;
    focusedField?: string;
};

export function PoolRoll(props: PoolRollProps) {
    const [count, setCount] = useState(
        props.rolled.value !== "" ? "1" : props.count.value,
    );
    const [rolled, setRolled] = useState(props.rolled.value);
    const countRef = useRef<HTMLInputElement>(null);
    const rollRef = useRef<HTMLInputElement>(null);
    const [table, setTable] = useState(props.table);
    const [preview, setPreview] = useState<{
        key: string;
        status: string;
        message: string;
    } | null>(null);
    const manual = rolled !== "";
    const previewKey = `${table}:${rolled}`;
    const selectedTable = props.tables.find((option) => option.value === table);
    useEffect(() => {
        if (!rolled || !table || !props.previewUrl) return;
        const controller = new AbortController();
        const key = `${table}:${rolled}`;
        const timer = window.setTimeout(async () => {
            try {
                const url = new URL(props.previewUrl, window.location.origin);
                url.searchParams.set("type", props.assetType);
                url.searchParams.set("table", table);
                url.searchParams.set("rolled", rolled);
                const response = await fetch(url, {
                    signal: controller.signal,
                    headers: { Accept: "application/json" },
                });
                if (!response.ok) throw new Error("Preview unavailable");
                const result = await response.json();
                if (!controller.signal.aborted) setPreview({ key, ...result });
            } catch {
                if (!controller.signal.aborted)
                    setPreview({
                        key,
                        status: "unavailable",
                        message:
                            "Preview unavailable. You can still submit your roll.",
                    });
            }
        }, 200);
        return () => {
            window.clearTimeout(timer);
            controller.abort();
        };
    }, [rolled, table, props.previewUrl, props.assetType]);
    const rangesId = useId();

    useLayoutEffect(() => {
        if (props.focusedField === "count") countRef.current?.focus();
        if (props.focusedField === "rolled") rollRef.current?.focus();
    }, [props.focusedField]);

    return (
        <>
            {props.tables.length === 1 ? (
                <>
                    <input
                        id="pool-table"
                        type="hidden"
                        name="table"
                        value={table}
                    />
                    <dl className="space-y-1">
                        <dt className="text-base font-semibold text-ink-900 dark:text-ink-100">
                            Table
                        </dt>
                        <dd className="text-base">
                            {selectedTable?.label}{" "}
                            <span className="text-muted">
                                · {selectedTable?.die}
                            </span>
                        </dd>
                    </dl>
                    {props.tableErrors.length > 0 && (
                        <Callout>
                            {props.tableErrors.map((error, index) => (
                                <p key={index}>{error}</p>
                            ))}
                        </Callout>
                    )}
                </>
            ) : (
                <RadioCards
                    legend="Table"
                    errors={props.tableErrors}
                    min="12rem"
                >
                    {props.tables.map((option) => (
                        <RadioCard
                            key={option.value}
                            name="table"
                            value={option.value}
                            label={option.label}
                            description={option.die}
                            checked={table === option.value}
                            onChange={() => setTable(option.value)}
                        />
                    ))}
                </RadioCards>
            )}
            <Field
                label={props.count.label}
                htmlFor="pool-count"
                errors={props.count.errors}
                description={
                    manual
                        ? "Your own roll adds one result. Clear ‘Your own roll’ to roll more."
                        : props.count.helpText
                }
            >
                <Input
                    ref={countRef}
                    id="pool-count"
                    name="count"
                    type="number"
                    min={1}
                    max={100}
                    required
                    inputMode="numeric"
                    value={manual ? "1" : count}
                    readOnly={manual}
                    onChange={(event) => setCount(event.target.value)}
                />
            </Field>
            <Field
                label={props.rolled.label}
                htmlFor="pool-roll"
                errors={props.rolled.errors}
                description={props.rolled.helpText}
            >
                <Input
                    ref={rollRef}
                    id="pool-roll"
                    name="rolled"
                    type="number"
                    min={1}
                    inputMode="numeric"
                    autoComplete="off"
                    aria-describedby={rangesId}
                    value={rolled}
                    onChange={(event) => {
                        setRolled(event.target.value);
                        if (event.target.value !== "") setCount("1");
                    }}
                />
            </Field>
            <div id={rangesId} className="text-sm text-muted">
                {selectedTable && (
                    <p>
                        A {selectedTable.die} roll is {selectedTable.lowest} to{" "}
                        {selectedTable.highest}.
                    </p>
                )}
            </div>
            <div role="status" aria-live="polite" className="text-sm">
                {manual &&
                    props.previewUrl &&
                    (preview?.key === previewKey ? (
                        <p>
                            {preview.status === "valid"
                                ? `Preview: ${preview.message}.`
                                : preview.message}
                        </p>
                    ) : (
                        <p className="text-muted">Checking this roll…</p>
                    ))}
            </div>
        </>
    );
}
