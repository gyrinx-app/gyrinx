import { useState } from "react";
import {
    Button,
    ButtonLink,
    Checkbox,
    Field,
    Input,
    NativeSelect,
    FieldErrors,
    Card,
    FormActions,
} from "../../ui";

type Option = {
    key: string;
    name: string;
    list_price: number;
    discount: number;
    payment: number;
};
type Line = {
    key: string;
    source: string;
    name: string;
    kind: string;
    amount: number;
    quantity: number;
    parts: {
        label: string;
        amount: number;
        detail?: string;
        replaced?: boolean;
    }[];
    options: Option[];
    blocked: string;
    claimed: string;
};
type Gang = {
    gang_id: string;
    name: string;
    credits: number | null;
    lines: Line[];
    receipt_id: string;
};
type Row = { skip: boolean; option?: string; name?: string };
type Selection = { comment: string; lines: Record<string, Row> };
export type CycleRewardsProps = {
    label: string;
    token: string;
    gangs: Gang[];
    receipts: Record<string, string>;
    csrf: string;
    problem?: string;
    focusGang?: string;
    readOnly?: boolean;
    submitted?: Record<string, Selection>;
};

function initial(gangs: Gang[], submitted?: Record<string, Selection>) {
    return Object.fromEntries(
        gangs
            .filter((gang) => !gang.receipt_id)
            .map((gang) => [
                gang.gang_id,
                {
                    comment: submitted?.[gang.gang_id]?.comment ?? "",
                    lines: Object.fromEntries(
                        gang.lines.map((line) => [
                            line.key,
                            {
                                skip:
                                    Boolean(line.claimed) ||
                                    Boolean(
                                        submitted?.[gang.gang_id]?.lines[
                                            line.key
                                        ]?.skip,
                                    ),
                                option:
                                    line.options.find(
                                        (option) =>
                                            option.key ===
                                            submitted?.[gang.gang_id]?.lines[
                                                line.key
                                            ]?.option,
                                    )?.key ??
                                    line.options[0]?.key ??
                                    "",
                                name:
                                    submitted?.[gang.gang_id]?.lines[line.key]
                                        ?.name ??
                                    line.options[0]?.name ??
                                    "",
                            },
                        ]),
                    ),
                },
            ]),
    ) as Record<string, Selection>;
}

export function CycleRewards({
    label,
    token,
    gangs,
    receipts,
    csrf,
    problem = "",
    focusGang = "",
    submitted,
    readOnly = false,
}: CycleRewardsProps) {
    const [draft, setDraft] = useState(() => initial(gangs, submitted));
    const [selected, setSelected] = useState(() =>
        gangs
            .filter(
                (gang) =>
                    !gang.receipt_id &&
                    (submitted
                        ? Object.hasOwn(submitted, gang.gang_id)
                        : !focusGang || gang.gang_id === focusGang),
            )
            .map((gang) => gang.gang_id),
    );
    const [pending, setPending] = useState(false);
    const change = (gang: string, key: string, fields: Partial<Row>) =>
        setDraft((old) => ({
            ...old,
            [gang]: {
                ...old[gang],
                lines: {
                    ...old[gang].lines,
                    [key]: { ...old[gang].lines[key], ...fields },
                },
            },
        }));
    const payload = Object.fromEntries(selected.map((id) => [id, draft[id]]));
    const canApply =
        selected.length > 0 &&
        selected.every((id) =>
            gangs
                .find((gang) => gang.gang_id === id)!
                .lines.every(
                    (line) =>
                        line.claimed ||
                        draft[id].lines[line.key].skip ||
                        (!line.blocked &&
                            (line.kind !== "recruitment" ||
                                Boolean(
                                    draft[id].lines[line.key].option &&
                                    draft[id].lines[line.key].name?.trim(),
                                ))),
                ),
        );
    return (
        <form
            method="post"
            className="space-y-6"
            onSubmit={(event) => {
                if (readOnly || pending || !canApply) event.preventDefault();
                else setPending(true);
            }}
        >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrf} />
            <input type="hidden" name="token" value={token} />
            <input
                type="hidden"
                name="selections"
                value={JSON.stringify(payload)}
            />
            {problem && <FieldErrors errors={[problem]} />}
            {gangs.map((gang, gangIndex) => {
                const active = selected.includes(gang.gang_id);
                const selection = draft[gang.gang_id];
                const income = gang.lines.reduce(
                    (sum, line) =>
                        sum +
                        (line.kind === "income" &&
                        !selection?.lines[line.key].skip &&
                        !line.claimed &&
                        !line.blocked
                            ? line.amount
                            : 0),
                    0,
                );
                const payment = gang.lines.reduce(
                    (sum, line) =>
                        sum +
                        (line.kind === "recruitment" &&
                        !selection?.lines[line.key].skip &&
                        !line.claimed &&
                        !line.blocked
                            ? (line.options.find(
                                  (option) =>
                                      option.key ===
                                      selection?.lines[line.key].option,
                              )?.payment ?? 0)
                            : 0),
                    0,
                );
                return (
                    <Card key={gang.gang_id}>
                        <section
                            className="space-y-4"
                            aria-labelledby={`reward-gang-${gangIndex}`}
                        >
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <h2
                                    id={`reward-gang-${gangIndex}`}
                                    className="text-base font-semibold"
                                >
                                    {gang.name}
                                </h2>
                                {gang.receipt_id ? (
                                    <ButtonLink
                                        href={receipts[gang.gang_id]}
                                        size="sm"
                                    >
                                        View receipt
                                    </ButtonLink>
                                ) : readOnly ? (
                                    <span className="text-sm text-muted">
                                        Pending
                                    </span>
                                ) : (
                                    <label className="flex items-center gap-2 text-sm">
                                        <Checkbox
                                            checked={active}
                                            aria-label={`Apply boons for ${gang.name}`}
                                            onChange={(event) =>
                                                setSelected((old) =>
                                                    event.target.checked
                                                        ? [...old, gang.gang_id]
                                                        : old.filter(
                                                              (id) =>
                                                                  id !==
                                                                  gang.gang_id,
                                                          ),
                                                )
                                            }
                                        />
                                        Apply for this gang
                                    </label>
                                )}
                            </div>
                            {gang.receipt_id ? (
                                <p className="text-sm text-muted">
                                    Boons applied for {label}.
                                </p>
                            ) : (
                                <>
                                    <div className="divide-y divide-box-border">
                                        {gang.lines.map((line, lineIndex) => {
                                            const row =
                                                selection.lines[line.key];
                                            const id = `reward-${gangIndex}-${lineIndex}`;
                                            const option = line.options.find(
                                                (option) =>
                                                    option.key === row.option,
                                            );
                                            return (
                                                <div
                                                    key={line.key}
                                                    className="space-y-3 py-4"
                                                >
                                                    <div className="flex items-start justify-between gap-4">
                                                        <div className="space-y-1">
                                                            <h3 className="font-semibold">
                                                                {line.name}
                                                            </h3>
                                                        </div>
                                                        {!readOnly && (
                                                            <label className="flex shrink-0 items-center gap-2 text-sm">
                                                                <Checkbox
                                                                    checked={
                                                                        row.skip
                                                                    }
                                                                    disabled={
                                                                        !active ||
                                                                        pending ||
                                                                        Boolean(
                                                                            line.claimed,
                                                                        )
                                                                    }
                                                                    aria-label={`Skip ${line.name} ${line.kind}`}
                                                                    onChange={(
                                                                        event,
                                                                    ) =>
                                                                        change(
                                                                            gang.gang_id,
                                                                            line.key,
                                                                            {
                                                                                skip: event
                                                                                    .target
                                                                                    .checked,
                                                                            },
                                                                        )
                                                                    }
                                                                />
                                                                Skip
                                                            </label>
                                                        )}
                                                    </div>
                                                    <p
                                                        className={
                                                            row.skip
                                                                ? "flex justify-between gap-4 text-sm text-muted line-through"
                                                                : "flex justify-between gap-4 text-sm"
                                                        }
                                                    >
                                                        {line.kind ===
                                                        "income" ? (
                                                            <>
                                                                <span>
                                                                    Income
                                                                </span>
                                                                <span className="text-right tabular-nums">
                                                                    +
                                                                    {
                                                                        line.amount
                                                                    }
                                                                    ¢
                                                                </span>
                                                            </>
                                                        ) : line.kind ===
                                                          "equipment" ? (
                                                            `${line.quantity} × ${line.parts[0]?.label} to stash`
                                                        ) : (
                                                            "Recruitment discount"
                                                        )}
                                                    </p>
                                                    {line.claimed && (
                                                        <p className="text-sm text-muted">
                                                            Already resolved by{" "}
                                                            {line.claimed} in
                                                            this cycle.
                                                        </p>
                                                    )}
                                                    {line.blocked &&
                                                        !line.claimed && (
                                                            <p className="text-sm text-muted">
                                                                {line.blocked}
                                                            </p>
                                                        )}
                                                    {line.kind === "income" &&
                                                        line.parts.length >
                                                            0 && (
                                                            <dl className="space-y-1 text-sm text-muted">
                                                                {line.parts.map(
                                                                    (
                                                                        part,
                                                                        index,
                                                                    ) => (
                                                                        <div
                                                                            key={
                                                                                index
                                                                            }
                                                                            className="flex items-start justify-between gap-4"
                                                                        >
                                                                            <dt className="min-w-0">
                                                                                {
                                                                                    part.label
                                                                                }
                                                                                {part.detail &&
                                                                                    ` · ${part.detail}`}
                                                                                {part.replaced &&
                                                                                    " · Replaced by override"}
                                                                            </dt>
                                                                            <dd className="shrink-0 text-right tabular-nums">
                                                                                {part.replaced ? (
                                                                                    <del>
                                                                                        {
                                                                                            part.amount
                                                                                        }

                                                                                        ¢
                                                                                    </del>
                                                                                ) : (
                                                                                    `${part.amount}¢`
                                                                                )}
                                                                            </dd>
                                                                        </div>
                                                                    ),
                                                                )}
                                                            </dl>
                                                        )}
                                                    {line.kind ===
                                                        "recruitment" &&
                                                        !row.skip &&
                                                        !line.claimed &&
                                                        !line.blocked && (
                                                            <div className="grid gap-3 sm:grid-cols-2">
                                                                <Field
                                                                    label="Fighter"
                                                                    htmlFor={`${id}-profile`}
                                                                >
                                                                    <NativeSelect
                                                                        value={
                                                                            row.option
                                                                        }
                                                                        disabled={
                                                                            readOnly ||
                                                                            !active ||
                                                                            pending
                                                                        }
                                                                        onChange={(
                                                                            event,
                                                                        ) =>
                                                                            change(
                                                                                gang.gang_id,
                                                                                line.key,
                                                                                {
                                                                                    option: event
                                                                                        .target
                                                                                        .value,
                                                                                    name:
                                                                                        line.options.find(
                                                                                            (
                                                                                                option,
                                                                                            ) =>
                                                                                                option.key ===
                                                                                                event
                                                                                                    .target
                                                                                                    .value,
                                                                                        )
                                                                                            ?.name ??
                                                                                        "",
                                                                                },
                                                                            )
                                                                        }
                                                                    >
                                                                        {line.options.map(
                                                                            (
                                                                                option,
                                                                            ) => (
                                                                                <option
                                                                                    key={
                                                                                        option.key
                                                                                    }
                                                                                    value={
                                                                                        option.key
                                                                                    }
                                                                                >
                                                                                    {
                                                                                        option.name
                                                                                    }{" "}
                                                                                    ·{" "}
                                                                                    {
                                                                                        option.payment
                                                                                    }

                                                                                    ¢
                                                                                </option>
                                                                            ),
                                                                        )}
                                                                    </NativeSelect>
                                                                </Field>
                                                                <Field
                                                                    label="Model name"
                                                                    htmlFor={`${id}-name`}
                                                                >
                                                                    <Input
                                                                        value={
                                                                            row.name
                                                                        }
                                                                        maxLength={
                                                                            200
                                                                        }
                                                                        required={
                                                                            active
                                                                        }
                                                                        disabled={
                                                                            readOnly ||
                                                                            !active ||
                                                                            pending
                                                                        }
                                                                        onChange={(
                                                                            event,
                                                                        ) =>
                                                                            change(
                                                                                gang.gang_id,
                                                                                line.key,
                                                                                {
                                                                                    name: event
                                                                                        .target
                                                                                        .value,
                                                                                },
                                                                            )
                                                                        }
                                                                    />
                                                                </Field>
                                                                {option && (
                                                                    <p className="text-sm text-muted sm:col-span-2">
                                                                        Price{" "}
                                                                        {
                                                                            option.list_price
                                                                        }
                                                                        ¢ −
                                                                        discount{" "}
                                                                        {
                                                                            option.discount
                                                                        }
                                                                        ¢ =
                                                                        payment{" "}
                                                                        {
                                                                            option.payment
                                                                        }
                                                                        ¢. The
                                                                        model
                                                                        retains
                                                                        its full
                                                                        rating.
                                                                    </p>
                                                                )}
                                                            </div>
                                                        )}
                                                </div>
                                            );
                                        })}
                                        {gang.lines.length === 0 && (
                                            <p className="py-4 text-sm text-muted">
                                                No rewards available. Applying
                                                records this gang as resolved
                                                for the cycle.
                                            </p>
                                        )}
                                    </div>
                                    <p className="text-sm" aria-live="polite">
                                        Income +{income}¢ · Recruitment −
                                        {payment}¢
                                        {gang.credits !== null &&
                                            ` · Credits after ${gang.credits + income - payment}¢`}
                                    </p>
                                    {!readOnly && (
                                        <Field
                                            label="Comment"
                                            htmlFor={`reward-comment-${gangIndex}`}
                                            description="Optional. Explain skipped or manually handled rewards."
                                        >
                                            <Input
                                                value={selection.comment}
                                                maxLength={255}
                                                disabled={!active || pending}
                                                onChange={(event) =>
                                                    setDraft((old) => ({
                                                        ...old,
                                                        [gang.gang_id]: {
                                                            ...old[
                                                                gang.gang_id
                                                            ],
                                                            comment:
                                                                event.target
                                                                    .value,
                                                        },
                                                    }))
                                                }
                                            />
                                        </Field>
                                    )}
                                </>
                            )}
                        </section>
                    </Card>
                );
            })}
            <div className="border-t border-box-border pt-4">
                {readOnly ? (
                    <p className="text-sm text-muted">
                        Only the campaign arbitrator can apply these rewards.
                    </p>
                ) : (
                    <FormActions>
                        <Button
                            variant="success"
                            type="submit"
                            disabled={!canApply || pending}
                        >
                            {pending
                                ? "Applying boons…"
                                : `Apply boons for ${selected.length} ${selected.length === 1 ? "gang" : "gangs"}`}
                        </Button>
                        <p className="text-sm text-muted">
                            Unselected gangs stay pending. Selected gangs are
                            resolved for this cycle, including skipped rewards.
                        </p>
                    </FormActions>
                )}
            </div>
        </form>
    );
}
