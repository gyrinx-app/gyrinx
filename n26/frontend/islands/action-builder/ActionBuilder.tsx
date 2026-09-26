import { useState } from "react";
import { Button, ButtonLink, Input, NativeSelect } from "../../ui";

type Option = { value: string; label: string };
type RankOption = Option & { counter: string };
type OutcomeOption = Option & { detail: string };
type Price = {
    resource: "credits" | "counter";
    payer: "gang" | "fighter";
    counter: string;
    amount: string;
};
type Change = {
    kind: "counter" | "picks";
    counter: string;
    mode: "set" | "add" | "subtract";
    amount: string;
    slotType: string;
};
type Outcome = {
    existing: string;
    name: string;
    operation: "augment" | "advancement" | "changes";
    slotType: string;
    slot: string;
    changes: Change[];
};
type Draft = {
    name: string;
    timing: "recruitment" | "post_cycle";
    acquisitionPrice: string;
    useMode: "paid" | "recruitment" | "rank" | "free";
    prices: Price[];
    rankCounter: string;
    rankTable: string;
    outcomes: Outcome[];
};
export type ActionBuilderProps = {
    draft: string;
    counters: Option[];
    rankTables: RankOption[];
    slotTypes: Option[];
    slots: Option[];
    outcomes: OutcomeOption[];
};

const field = "space-y-1.5";
const label = "block text-sm font-semibold text-ink-900 dark:text-ink-100";
const panel = "rounded-box border border-box-border bg-box p-5";

function Select({
    value,
    options,
    onChange,
    placeholder,
    labelText,
}: {
    value: string;
    options: Option[];
    onChange: (value: string) => void;
    placeholder?: string;
    labelText: string;
}) {
    return (
        <NativeSelect
            aria-label={labelText}
            value={value}
            onChange={(event) => onChange(event.target.value)}
        >
            <option value="">{placeholder || "Choose…"}</option>
            {options.map((option) => (
                <option key={option.value} value={option.value}>
                    {option.label}
                </option>
            ))}
        </NativeSelect>
    );
}

function defaultDraft(props: ActionBuilderProps): Draft {
    return {
        name: "",
        timing: "post_cycle",
        acquisitionPrice: "0",
        useMode: "paid",
        prices: [
            { resource: "credits", payer: "gang", counter: "", amount: "" },
        ],
        rankCounter: props.counters[0]?.value || "",
        rankTable: "",
        outcomes: [],
    };
}

function readDraft(props: ActionBuilderProps): Draft {
    if (!props.draft) return defaultDraft(props);
    try {
        return { ...defaultDraft(props), ...JSON.parse(props.draft) };
    } catch {
        return defaultDraft(props);
    }
}

function priceText(draft: Draft, props: ActionBuilderProps): string {
    if (draft.useMode === "recruitment") return "One use at recruitment";
    if (draft.useMode === "rank") return "Uses earned from ranks";
    if (draft.useMode === "free") return "No use price";
    if (
        !draft.prices.length ||
        draft.prices.some((price) => !price.amount || Number(price.amount) < 1)
    )
        return "";
    return draft.prices
        .map((price) =>
            price.resource === "credits"
                ? `${price.amount}¢`
                : `${price.amount} ${props.counters.find((counter) => counter.value === price.counter)?.label || "counter"}`,
        )
        .join(" + ");
}

function outcomeDetail(outcome: Outcome, props: ActionBuilderProps): string {
    if (outcome.existing)
        return (
            props.outcomes.find((item) => item.value === outcome.existing)
                ?.detail || "Existing outcome"
        );
    if (outcome.operation === "augment")
        return `Advance a carried item in ${props.slotTypes.find((item) => item.value === outcome.slotType)?.label || "the selected tier ladder"}`;
    if (outcome.operation === "advancement")
        return `Resolve the ${props.slots.find((item) => item.value === outcome.slot)?.label || "selected"} slot`;
    return outcome.changes
        .map((change) =>
            change.kind === "picks"
                ? `Remove picks from ${props.slotTypes.find((item) => item.value === change.slotType)?.label || "slot"}`
                : `${change.mode === "set" ? "Set" : change.mode === "add" ? "Add to" : "Subtract from"} ${props.counters.find((item) => item.value === change.counter)?.label || "counter"} ${change.mode === "set" ? "to" : "by"} ${change.amount || "?"}`,
        )
        .join("; ");
}

function issues(draft: Draft): string[] {
    const found: string[] = [];
    if (!draft.name.trim()) found.push("Name the action.");
    if (!draft.outcomes.length) found.push("Add at least one outcome.");
    draft.outcomes.forEach((outcome, index) => {
        if (outcome.existing) return;
        if (!outcome.name.trim()) found.push(`Name outcome ${index + 1}.`);
        if (outcome.operation === "augment" && !outcome.slotType)
            found.push(`Choose a tier slot type for outcome ${index + 1}.`);
        if (outcome.operation === "advancement" && !outcome.slot)
            found.push(`Choose an advancement slot for outcome ${index + 1}.`);
        if (outcome.operation === "changes" && !outcome.changes.length)
            found.push(`Add a change to outcome ${index + 1}.`);
    });
    if (
        draft.useMode === "paid" &&
        (!draft.prices.length ||
            draft.prices.some(
                (price) =>
                    !price.amount ||
                    Number(price.amount) < 1 ||
                    (price.resource === "counter" && !price.counter),
            ))
    )
        found.push("Set every part of the use price, or choose no use price.");
    if (draft.useMode === "rank" && !draft.rankTable)
        found.push("Choose a rank table.");
    return found;
}

export function ActionBuilder(props: ActionBuilderProps) {
    const [draft, setDraft] = useState<Draft>(() => readDraft(props));
    const [step, setStep] = useState(0);
    const [notice, setNotice] = useState("");
    const steps = ["Action", "Uses", "Outcomes", "Review"];
    const update = (change: Partial<Draft>) =>
        setDraft((old) => ({ ...old, ...change }));
    const editPrice = (at: number, change: Partial<Price>) =>
        update({
            prices: draft.prices.map((item, index) =>
                index === at ? { ...item, ...change } : item,
            ),
        });
    const editOutcome = (at: number, change: Partial<Outcome>) =>
        update({
            outcomes: draft.outcomes.map((item, index) =>
                index === at ? { ...item, ...change } : item,
            ),
        });
    const price = priceText(draft, props);
    const problems = issues(draft);
    const next = () => {
        if (step === 0 && !draft.name.trim()) {
            setNotice("Name the action before continuing.");
            return;
        }
        setNotice("");
        setStep(Math.min(step + 1, 3));
    };
    return (
        <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_20rem]">
            <div className="min-w-0">
                <nav
                    aria-label="Action setup steps"
                    className="mb-6 flex flex-wrap gap-2"
                >
                    {steps.map((name, index) => (
                        <button
                            key={name}
                            type="button"
                            onClick={() => setStep(index)}
                            aria-current={step === index ? "step" : undefined}
                            className={`rounded-full border px-4 py-2 text-sm font-medium ${step === index ? "border-accent text-ink-900 dark:text-ink-100" : "border-box-border text-muted"}`}
                        >
                            {index + 1}. {name}
                        </button>
                    ))}
                </nav>
                <div className={`${panel} space-y-6`}>
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                            Step {step + 1} of 4
                        </p>
                        <h2 className="mt-1 text-xl font-semibold">
                            {
                                [
                                    "Name and timing",
                                    "How uses work",
                                    "Outcomes",
                                    "Review action",
                                ][step]
                            }
                        </h2>
                    </div>
                    {step === 0 && (
                        <>
                            <div className={field}>
                                <label className={label} htmlFor="action-name">
                                    Action name
                                </label>
                                <Input
                                    id="action-name"
                                    value={draft.name}
                                    onChange={(event) =>
                                        update({ name: event.target.value })
                                    }
                                    placeholder="e.g. Suit Evolution"
                                />
                            </div>
                            <fieldset className={field}>
                                <legend className={label}>
                                    When can it start?
                                </legend>
                                <div className="grid gap-3 sm:grid-cols-2">
                                    {(
                                        [
                                            [
                                                "recruitment",
                                                "At recruitment",
                                                "As the fighter is hired.",
                                            ],
                                            [
                                                "post_cycle",
                                                "After a cycle",
                                                "On the fighter's edit page.",
                                            ],
                                        ] as const
                                    ).map(([value, title, description]) => (
                                        <label
                                            key={value}
                                            className={`flex cursor-pointer gap-3 rounded-box border p-4 ${draft.timing === value ? "border-accent" : "border-box-border"}`}
                                        >
                                            <input
                                                type="radio"
                                                name="timing-ui"
                                                checked={draft.timing === value}
                                                onChange={() =>
                                                    update({ timing: value })
                                                }
                                            />
                                            <span>
                                                <strong className="block">
                                                    {title}
                                                </strong>
                                                <span className="text-sm text-muted">
                                                    {description}
                                                </span>
                                            </span>
                                        </label>
                                    ))}
                                </div>
                            </fieldset>
                            <details>
                                <summary className="cursor-pointer text-sm font-medium">
                                    Acquisition price
                                </summary>
                                <div className="mt-3 max-w-xs">
                                    <label
                                        className={label}
                                        htmlFor="acquisition-price"
                                    >
                                        Price to acquire (¢)
                                    </label>
                                    <Input
                                        id="acquisition-price"
                                        type="number"
                                        min="0"
                                        value={draft.acquisitionPrice}
                                        onChange={(event) =>
                                            update({
                                                acquisitionPrice:
                                                    event.target.value,
                                            })
                                        }
                                    />
                                    <p className="mt-1 text-xs text-muted">
                                        This is separate from the price paid
                                        each time the action is used.
                                    </p>
                                </div>
                            </details>
                        </>
                    )}
                    {step === 1 && (
                        <>
                            <p className="text-sm text-muted">
                                Choose whether a fighter pays for each use or
                                earns a limited allowance.
                            </p>
                            <div className="grid gap-3 sm:grid-cols-2">
                                {(
                                    [
                                        [
                                            "paid",
                                            "Pay each time",
                                            "Spend credits, a counter, or both.",
                                        ],
                                        [
                                            "recruitment",
                                            "Earn one use at recruitment",
                                            "One use when recruitment completes.",
                                        ],
                                        [
                                            "rank",
                                            "Earn uses from a rank table",
                                            "One use per threshold crossed.",
                                        ],
                                        [
                                            "free",
                                            "No use price",
                                            "No payment or allowance.",
                                        ],
                                    ] as const
                                ).map(([value, title, description]) => (
                                    <label
                                        key={value}
                                        className={`flex cursor-pointer gap-3 rounded-box border p-4 ${draft.useMode === value ? "border-accent" : "border-box-border"}`}
                                    >
                                        <input
                                            type="radio"
                                            name="use-mode-ui"
                                            checked={draft.useMode === value}
                                            onChange={() =>
                                                update({
                                                    useMode: value,
                                                    timing:
                                                        value === "recruitment"
                                                            ? "recruitment"
                                                            : value === "rank"
                                                              ? "post_cycle"
                                                              : draft.timing,
                                                })
                                            }
                                        />
                                        <span>
                                            <strong className="block">
                                                {title}
                                            </strong>
                                            <span className="text-sm text-muted">
                                                {description}
                                            </span>
                                        </span>
                                    </label>
                                ))}
                            </div>
                            {draft.useMode === "paid" && (
                                <section className="space-y-4 border-t border-box-border pt-5">
                                    <h3 className="font-semibold">
                                        Price per use
                                    </h3>
                                    {draft.prices.map((item, index) => (
                                        <div
                                            key={index}
                                            className="grid items-end gap-3 rounded-box border border-box-border p-3 sm:grid-cols-2 lg:grid-cols-4"
                                        >
                                            <div className={field}>
                                                <label className={label}>
                                                    Resource
                                                </label>
                                                <Select
                                                    labelText={`Price ${index + 1} resource`}
                                                    value={item.resource}
                                                    options={[
                                                        {
                                                            value: "credits",
                                                            label: "Credits",
                                                        },
                                                        {
                                                            value: "counter",
                                                            label: "Counter",
                                                        },
                                                    ]}
                                                    onChange={(value) =>
                                                        editPrice(index, {
                                                            resource:
                                                                value as Price["resource"],
                                                            payer:
                                                                value ===
                                                                "credits"
                                                                    ? "gang"
                                                                    : "fighter",
                                                        })
                                                    }
                                                />
                                            </div>
                                            {item.resource === "counter" ? (
                                                <div className={field}>
                                                    <label className={label}>
                                                        Counter
                                                    </label>
                                                    <Select
                                                        labelText={`Price ${index + 1} counter`}
                                                        value={item.counter}
                                                        options={props.counters}
                                                        onChange={(value) =>
                                                            editPrice(index, {
                                                                counter: value,
                                                            })
                                                        }
                                                    />
                                                </div>
                                            ) : (
                                                <div className={field}>
                                                    <label className={label}>
                                                        Paid by
                                                    </label>
                                                    <p className="py-2 text-sm">
                                                        Gang
                                                    </p>
                                                </div>
                                            )}
                                            <div className={field}>
                                                <label className={label}>
                                                    Amount
                                                </label>
                                                <Input
                                                    aria-label={`Price ${index + 1} amount`}
                                                    type="number"
                                                    min="1"
                                                    value={item.amount}
                                                    onChange={(event) =>
                                                        editPrice(index, {
                                                            amount: event.target
                                                                .value,
                                                        })
                                                    }
                                                    placeholder="Enter amount"
                                                />
                                            </div>
                                            <div className="flex gap-2">
                                                {item.resource ===
                                                    "counter" && (
                                                    <NativeSelect
                                                        aria-label="Paid by"
                                                        value={item.payer}
                                                        onChange={(event) =>
                                                            editPrice(index, {
                                                                payer: event
                                                                    .target
                                                                    .value as Price["payer"],
                                                            })
                                                        }
                                                    >
                                                        <option value="fighter">
                                                            Fighter
                                                        </option>
                                                        <option value="gang">
                                                            Gang
                                                        </option>
                                                    </NativeSelect>
                                                )}
                                                <Button
                                                    variant="ghost"
                                                    aria-label="Remove price part"
                                                    onClick={() =>
                                                        update({
                                                            prices: draft.prices.filter(
                                                                (_, i) =>
                                                                    i !== index,
                                                            ),
                                                        })
                                                    }
                                                >
                                                    Remove
                                                </Button>
                                            </div>
                                        </div>
                                    ))}
                                    <Button
                                        variant="ghost"
                                        onClick={() =>
                                            update({
                                                prices: [
                                                    ...draft.prices,
                                                    {
                                                        resource: "credits",
                                                        payer: "gang",
                                                        counter: "",
                                                        amount: "",
                                                    },
                                                ],
                                            })
                                        }
                                    >
                                        + Add another part
                                    </Button>
                                </section>
                            )}
                            {draft.useMode === "rank" && (
                                <div className="grid gap-4 sm:grid-cols-2">
                                    <div className={field}>
                                        <label className={label}>Counter</label>
                                        <Select
                                            labelText="Rank counter"
                                            value={draft.rankCounter}
                                            options={props.counters}
                                            onChange={(value) =>
                                                update({
                                                    rankCounter: value,
                                                    rankTable: "",
                                                })
                                            }
                                        />
                                    </div>
                                    <div className={field}>
                                        <label className={label}>
                                            Rank table
                                        </label>
                                        <Select
                                            labelText="Rank table"
                                            value={draft.rankTable}
                                            options={props.rankTables.filter(
                                                (row) =>
                                                    row.counter ===
                                                    draft.rankCounter,
                                            )}
                                            onChange={(value) =>
                                                update({ rankTable: value })
                                            }
                                        />
                                    </div>
                                    <p className="sm:col-span-2 text-sm text-muted">
                                        The action tracks this counter. Each
                                        fighter earns uses from the rank table
                                        it holds. Selecting a table here does
                                        not grant it to anyone.
                                    </p>
                                </div>
                            )}
                        </>
                    )}
                    {step === 2 && (
                        <>
                            <p className="text-sm text-muted">
                                Add what the action can do. If there is more
                                than one outcome, the player chooses one.
                            </p>
                            {draft.outcomes.length === 0 && (
                                <p className="rounded-box border border-dashed border-box-border p-4 text-sm text-muted">
                                    No outcomes yet. Add at least one result.
                                </p>
                            )}
                            {draft.outcomes.map((outcome, index) => (
                                <section
                                    key={index}
                                    className="space-y-4 rounded-box border border-box-border p-4"
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <p className="text-xs font-semibold uppercase text-muted">
                                                Outcome {index + 1}
                                            </p>
                                            <h3 className="font-semibold">
                                                {outcome.existing
                                                    ? props.outcomes.find(
                                                          (row) =>
                                                              row.value ===
                                                              outcome.existing,
                                                      )?.label
                                                    : outcome.name ||
                                                      "New outcome"}
                                            </h3>
                                        </div>
                                        <div className="flex flex-wrap gap-1">
                                            <Button
                                                variant="ghost"
                                                aria-label="Move outcome up"
                                                disabled={index === 0}
                                                onClick={() => {
                                                    const rows = [
                                                        ...draft.outcomes,
                                                    ];
                                                    [
                                                        rows[index - 1],
                                                        rows[index],
                                                    ] = [
                                                        rows[index],
                                                        rows[index - 1],
                                                    ];
                                                    update({ outcomes: rows });
                                                }}
                                            >
                                                ↑
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                aria-label="Move outcome down"
                                                disabled={
                                                    index ===
                                                    draft.outcomes.length - 1
                                                }
                                                onClick={() => {
                                                    const rows = [
                                                        ...draft.outcomes,
                                                    ];
                                                    [
                                                        rows[index + 1],
                                                        rows[index],
                                                    ] = [
                                                        rows[index],
                                                        rows[index + 1],
                                                    ];
                                                    update({ outcomes: rows });
                                                }}
                                            >
                                                ↓
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                onClick={() =>
                                                    update({
                                                        outcomes:
                                                            draft.outcomes.filter(
                                                                (_, i) =>
                                                                    i !== index,
                                                            ),
                                                    })
                                                }
                                            >
                                                Remove
                                            </Button>
                                        </div>
                                    </div>
                                    {outcome.existing ? (
                                        <div className={field}>
                                            <label className={label}>
                                                Existing outcome
                                            </label>
                                            <Select
                                                labelText={`Outcome ${index + 1} existing result`}
                                                value={outcome.existing}
                                                options={props.outcomes}
                                                onChange={(value) =>
                                                    editOutcome(index, {
                                                        existing: value,
                                                    })
                                                }
                                            />
                                            <p className="text-sm text-muted">
                                                {outcomeDetail(outcome, props)}
                                            </p>
                                        </div>
                                    ) : (
                                        <>
                                            <div className={field}>
                                                <label className={label}>
                                                    Outcome name
                                                </label>
                                                <Input
                                                    aria-label={`Outcome ${index + 1} name`}
                                                    value={outcome.name}
                                                    onChange={(event) =>
                                                        editOutcome(index, {
                                                            name: event.target
                                                                .value,
                                                        })
                                                    }
                                                    placeholder="e.g. Clear glitches"
                                                />
                                                <p className="text-xs text-muted">
                                                    Shown when the action has
                                                    more than one possible
                                                    result.
                                                </p>
                                            </div>
                                            <div className={field}>
                                                <label className={label}>
                                                    What happens?
                                                </label>
                                                <Select
                                                    labelText={`Outcome ${index + 1} operation`}
                                                    value={outcome.operation}
                                                    options={[
                                                        {
                                                            value: "augment",
                                                            label: "Augment a carried item",
                                                        },
                                                        {
                                                            value: "advancement",
                                                            label: "Resolve advancement",
                                                        },
                                                        {
                                                            value: "changes",
                                                            label: "Apply changes",
                                                        },
                                                    ]}
                                                    onChange={(value) =>
                                                        editOutcome(index, {
                                                            operation:
                                                                value as Outcome["operation"],
                                                        })
                                                    }
                                                />
                                            </div>
                                            {outcome.operation ===
                                                "augment" && (
                                                <div className={field}>
                                                    <label className={label}>
                                                        Tier slot type
                                                    </label>
                                                    <Select
                                                        labelText={`Outcome ${index + 1} tier slot type`}
                                                        value={outcome.slotType}
                                                        options={
                                                            props.slotTypes
                                                        }
                                                        onChange={(value) =>
                                                            editOutcome(index, {
                                                                slotType: value,
                                                            })
                                                        }
                                                    />
                                                </div>
                                            )}
                                            {outcome.operation ===
                                                "advancement" && (
                                                <div className={field}>
                                                    <label className={label}>
                                                        Advancement slot
                                                    </label>
                                                    <Select
                                                        labelText={`Outcome ${index + 1} advancement slot`}
                                                        value={outcome.slot}
                                                        options={props.slots}
                                                        onChange={(value) =>
                                                            editOutcome(index, {
                                                                slot: value,
                                                            })
                                                        }
                                                    />
                                                </div>
                                            )}
                                            {outcome.operation ===
                                                "changes" && (
                                                <div className="space-y-3">
                                                    <h4 className="font-medium">
                                                        Changes, in order
                                                    </h4>
                                                    {outcome.changes.map(
                                                        (change, at) => (
                                                            <div
                                                                key={at}
                                                                className="grid gap-2 rounded-box border border-box-border p-3 sm:grid-cols-2"
                                                            >
                                                                <Select
                                                                    labelText={`Outcome ${index + 1} change ${at + 1} type`}
                                                                    value={
                                                                        change.kind
                                                                    }
                                                                    options={[
                                                                        {
                                                                            value: "counter",
                                                                            label: "Change counter",
                                                                        },
                                                                        {
                                                                            value: "picks",
                                                                            label: "Remove picks",
                                                                        },
                                                                    ]}
                                                                    onChange={(
                                                                        value,
                                                                    ) =>
                                                                        editOutcome(
                                                                            index,
                                                                            {
                                                                                changes:
                                                                                    outcome.changes.map(
                                                                                        (
                                                                                            row,
                                                                                            i,
                                                                                        ) =>
                                                                                            i ===
                                                                                            at
                                                                                                ? {
                                                                                                      ...row,
                                                                                                      kind: value as Change["kind"],
                                                                                                  }
                                                                                                : row,
                                                                                    ),
                                                                            },
                                                                        )
                                                                    }
                                                                />
                                                                {change.kind ===
                                                                "counter" ? (
                                                                    <>
                                                                        <Select
                                                                            labelText={`Outcome ${index + 1} change ${at + 1} counter`}
                                                                            value={
                                                                                change.counter
                                                                            }
                                                                            options={
                                                                                props.counters
                                                                            }
                                                                            onChange={(
                                                                                value,
                                                                            ) =>
                                                                                editOutcome(
                                                                                    index,
                                                                                    {
                                                                                        changes:
                                                                                            outcome.changes.map(
                                                                                                (
                                                                                                    row,
                                                                                                    i,
                                                                                                ) =>
                                                                                                    i ===
                                                                                                    at
                                                                                                        ? {
                                                                                                              ...row,
                                                                                                              counter:
                                                                                                                  value,
                                                                                                          }
                                                                                                        : row,
                                                                                            ),
                                                                                    },
                                                                                )
                                                                            }
                                                                        />
                                                                        <Select
                                                                            labelText={`Outcome ${index + 1} change ${at + 1} mode`}
                                                                            value={
                                                                                change.mode
                                                                            }
                                                                            options={[
                                                                                {
                                                                                    value: "set",
                                                                                    label: "Set to",
                                                                                },
                                                                                {
                                                                                    value: "add",
                                                                                    label: "Add",
                                                                                },
                                                                                {
                                                                                    value: "subtract",
                                                                                    label: "Subtract",
                                                                                },
                                                                            ]}
                                                                            onChange={(
                                                                                value,
                                                                            ) =>
                                                                                editOutcome(
                                                                                    index,
                                                                                    {
                                                                                        changes:
                                                                                            outcome.changes.map(
                                                                                                (
                                                                                                    row,
                                                                                                    i,
                                                                                                ) =>
                                                                                                    i ===
                                                                                                    at
                                                                                                        ? {
                                                                                                              ...row,
                                                                                                              mode: value as Change["mode"],
                                                                                                          }
                                                                                                        : row,
                                                                                            ),
                                                                                    },
                                                                                )
                                                                            }
                                                                        />
                                                                        <Input
                                                                            aria-label={`Outcome ${index + 1} change ${at + 1} amount`}
                                                                            type="number"
                                                                            min="0"
                                                                            value={
                                                                                change.amount
                                                                            }
                                                                            onChange={(
                                                                                event,
                                                                            ) =>
                                                                                editOutcome(
                                                                                    index,
                                                                                    {
                                                                                        changes:
                                                                                            outcome.changes.map(
                                                                                                (
                                                                                                    row,
                                                                                                    i,
                                                                                                ) =>
                                                                                                    i ===
                                                                                                    at
                                                                                                        ? {
                                                                                                              ...row,
                                                                                                              amount: event
                                                                                                                  .target
                                                                                                                  .value,
                                                                                                          }
                                                                                                        : row,
                                                                                            ),
                                                                                    },
                                                                                )
                                                                            }
                                                                        />
                                                                    </>
                                                                ) : (
                                                                    <Select
                                                                        labelText={`Outcome ${index + 1} change ${at + 1} slot type`}
                                                                        value={
                                                                            change.slotType
                                                                        }
                                                                        options={
                                                                            props.slotTypes
                                                                        }
                                                                        onChange={(
                                                                            value,
                                                                        ) =>
                                                                            editOutcome(
                                                                                index,
                                                                                {
                                                                                    changes:
                                                                                        outcome.changes.map(
                                                                                            (
                                                                                                row,
                                                                                                i,
                                                                                            ) =>
                                                                                                i ===
                                                                                                at
                                                                                                    ? {
                                                                                                          ...row,
                                                                                                          slotType:
                                                                                                              value,
                                                                                                      }
                                                                                                    : row,
                                                                                        ),
                                                                                },
                                                                            )
                                                                        }
                                                                    />
                                                                )}
                                                                <Button
                                                                    variant="ghost"
                                                                    onClick={() =>
                                                                        editOutcome(
                                                                            index,
                                                                            {
                                                                                changes:
                                                                                    outcome.changes.filter(
                                                                                        (
                                                                                            _,
                                                                                            i,
                                                                                        ) =>
                                                                                            i !==
                                                                                            at,
                                                                                    ),
                                                                            },
                                                                        )
                                                                    }
                                                                >
                                                                    Remove
                                                                    change
                                                                </Button>
                                                            </div>
                                                        ),
                                                    )}
                                                    <Button
                                                        variant="ghost"
                                                        onClick={() =>
                                                            editOutcome(index, {
                                                                changes: [
                                                                    ...outcome.changes,
                                                                    {
                                                                        kind: "counter",
                                                                        counter:
                                                                            "",
                                                                        mode: "set",
                                                                        amount: "0",
                                                                        slotType:
                                                                            "",
                                                                    },
                                                                ],
                                                            })
                                                        }
                                                    >
                                                        + Add change
                                                    </Button>
                                                </div>
                                            )}
                                        </>
                                    )}
                                </section>
                            ))}
                            <div className="flex flex-wrap gap-2">
                                <Button
                                    variant="primary"
                                    onClick={() =>
                                        update({
                                            outcomes: [
                                                ...draft.outcomes,
                                                {
                                                    existing: "",
                                                    name: "",
                                                    operation: "augment",
                                                    slotType: "",
                                                    slot: "",
                                                    changes: [],
                                                },
                                            ],
                                        })
                                    }
                                >
                                    + Create outcome
                                </Button>
                                <Button
                                    variant="default"
                                    disabled={!props.outcomes.length}
                                    onClick={() =>
                                        update({
                                            outcomes: [
                                                ...draft.outcomes,
                                                {
                                                    existing:
                                                        props.outcomes[0].value,
                                                    name: "",
                                                    operation: "augment",
                                                    slotType: "",
                                                    slot: "",
                                                    changes: [],
                                                },
                                            ],
                                        })
                                    }
                                >
                                    Use existing outcome
                                </Button>
                            </div>
                        </>
                    )}
                    {step === 3 && (
                        <>
                            <p className="text-sm text-muted">
                                Check the action, its uses and what each outcome
                                does. You can grant it after creating it.
                            </p>
                            <div className="divide-y divide-box-border rounded-box border border-box-border">
                                <section className="p-4">
                                    <h3 className="text-sm font-semibold text-muted">
                                        Action
                                    </h3>
                                    <p className="mt-2 font-semibold">
                                        {draft.name || "Unnamed action"}
                                    </p>
                                    <p className="text-sm">
                                        {draft.timing === "recruitment"
                                            ? "At recruitment"
                                            : "After a cycle"}
                                        {Number(draft.acquisitionPrice) > 0
                                            ? ` · ${draft.acquisitionPrice}¢ to acquire`
                                            : ""}
                                    </p>
                                </section>
                                <section className="p-4">
                                    <h3 className="text-sm font-semibold text-muted">
                                        Uses
                                    </h3>
                                    <p className="mt-2">
                                        {draft.useMode === "paid"
                                            ? price
                                                ? `Pay ${price} each time`
                                                : "Price not set"
                                            : price}
                                    </p>
                                </section>
                                <section className="p-4">
                                    <h3 className="text-sm font-semibold text-muted">
                                        Outcomes
                                    </h3>
                                    {draft.outcomes.map((outcome, index) => (
                                        <div
                                            key={index}
                                            className="mt-3 flex gap-3"
                                        >
                                            <span className="text-muted">
                                                {index + 1}.
                                            </span>
                                            <div>
                                                <strong className="block">
                                                    {outcome.existing
                                                        ? props.outcomes.find(
                                                              (row) =>
                                                                  row.value ===
                                                                  outcome.existing,
                                                          )?.label
                                                        : outcome.name ||
                                                          "Unnamed outcome"}
                                                </strong>
                                                <span className="block text-sm text-muted">
                                                    {outcomeDetail(
                                                        outcome,
                                                        props,
                                                    )}
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </section>
                            </div>
                            {problems.length ? (
                                <div
                                    role="alert"
                                    className="rounded-box border border-amber-500 p-4"
                                >
                                    <strong>Finish before creating</strong>
                                    <ul className="mt-2 list-inside list-disc text-sm">
                                        {problems.map((problem) => (
                                            <li key={problem}>{problem}</li>
                                        ))}
                                    </ul>
                                </div>
                            ) : (
                                <p className="text-sm">
                                    Ready to create. You can grant this action
                                    to fighter entries next.
                                </p>
                            )}
                            <input
                                type="hidden"
                                name="draft"
                                value={JSON.stringify(draft)}
                            />
                            <Button
                                type="submit"
                                variant="success"
                                disabled={problems.length > 0}
                            >
                                Create action
                            </Button>
                        </>
                    )}
                </div>
                {notice && (
                    <p
                        role="alert"
                        className="mt-3 text-sm text-red-700 dark:text-red-300"
                    >
                        {notice}
                    </p>
                )}
                <div className="mt-5 flex items-center justify-between gap-3">
                    <div>
                        {step > 0 ? (
                            <Button
                                variant="ghost"
                                onClick={() => setStep(step - 1)}
                            >
                                ← Back
                            </Button>
                        ) : (
                            <ButtonLink
                                href="/n26/authoring/action/"
                                variant="ghost"
                            >
                                Cancel
                            </ButtonLink>
                        )}
                    </div>
                    {step < 3 && (
                        <Button variant="primary" onClick={next}>
                            Continue →
                        </Button>
                    )}
                </div>
            </div>
            <aside className="self-start rounded-box border border-box-border p-5 xl:sticky xl:top-6">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Player view · approximate
                </p>
                <h2 className="mt-1 font-semibold">Action on fighter edit</h2>
                <div className="mt-4 rounded-box border border-box-border p-4">
                    <div className="flex justify-between gap-3">
                        <strong>{draft.name || "Action name"}</strong>
                        <span className="text-xs text-muted">
                            {draft.timing === "recruitment"
                                ? "At recruitment"
                                : "After a cycle"}
                        </span>
                    </div>
                    {price && (
                        <p className="mt-4 text-sm">
                            <span className="text-muted">
                                {draft.useMode === "paid"
                                    ? "Price"
                                    : "Available"}
                                :{" "}
                            </span>
                            <strong>
                                {draft.useMode === "free"
                                    ? "Free"
                                    : draft.useMode === "recruitment"
                                      ? "1 use"
                                      : draft.useMode === "rank"
                                        ? "From ranks"
                                        : price}
                            </strong>
                        </p>
                    )}
                    <span className="mt-4 inline-block text-sm font-semibold text-muted">
                        Start →
                    </span>
                </div>
                <p className="mt-3 text-xs text-muted">
                    This preview does not check grants or outcomes.
                </p>
            </aside>
        </div>
    );
}
