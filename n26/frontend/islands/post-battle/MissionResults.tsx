import { Button, Field, Icon, Input } from "../../ui";
import { Counters } from "./Counters";
import { value } from "./types";
import type { Draft } from "./useReportDraft";
export function MissionResults({ form }: { form: Draft }) {
    const d = form.display;
    const credits = d.mission.creditLines.reduce((total, line) => {
        const amount = Number(value(form, `credit-${line.id}-amount`) || 0);
        return total + (Number.isInteger(amount) && amount >= 0 ? amount : 0);
    }, 0);
    return (
        <fieldset className="min-w-0 scroll-mt-24 space-y-6 border border-box-border bg-surface p-4 sm:p-5">
            <legend className="sr-only">Mission results</legend>
            <div>
                <h2 className="text-lg font-semibold">Mission results</h2>
                <p className="mt-1 text-sm text-muted">
                    Enter the credits the gang gained and any change to its
                    counters.
                </p>
            </div>
            {d.territory && (
                <section
                    className="space-y-2 border border-box-border bg-ink-100 p-4 dark:bg-ink-900"
                    aria-labelledby="territory-result-heading"
                >
                    <h3
                        id="territory-result-heading"
                        className="text-sm font-medium text-muted"
                    >
                        {d.territory.heading}
                    </h3>
                    <p className="text-xl font-semibold">{d.territory.name}</p>
                    <p className="text-sm">{d.territory.outcome}</p>
                    {d.territory.currentHolder && (
                        <p className="text-sm text-muted">
                            {d.territory.currentHolder}
                        </p>
                    )}
                    <p className="flex items-center gap-2 text-xs text-muted">
                        {d.territory.applied && (
                            <Icon
                                name="check-check"
                                className="size-4 shrink-0"
                            />
                        )}
                        {d.territory.note}
                    </p>
                </section>
            )}
            <div className="space-y-3">
                <h3 id="credits-heading" className="text-lg font-semibold">
                    Credits
                </h3>
                <ul className="space-y-3" aria-labelledby="credits-heading">
                    {d.mission.creditLines.map((line) => (
                        <li
                            key={line.id}
                            className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 border-b border-box-border pb-3 last:border-0 last:pb-0 sm:grid-cols-[8rem_minmax(0,1fr)_auto]"
                        >
                            <div className="text-sm">
                                <Field
                                    label="Amount"
                                    htmlFor={`credit-${line.id}-amount`}
                                    errors={line.amountErrors}
                                >
                                    <Input
                                        id={`credit-${line.id}-amount`}
                                        name={`credit-${line.id}-amount`}
                                        type="number"
                                        min="0"
                                        inputMode="numeric"
                                        controlSize="lg"
                                        value={value(
                                            form,
                                            `credit-${line.id}-amount`,
                                        )}
                                        onChange={(event) =>
                                            form.change(
                                                `credit-${line.id}-amount`,
                                                event.currentTarget.value,
                                            )
                                        }
                                    />
                                </Field>
                            </div>
                            <div className="col-span-2 text-sm sm:col-span-1">
                                <Field
                                    label="Reason"
                                    htmlFor={`credit-${line.id}-reason`}
                                    errors={line.reasonErrors}
                                >
                                    <Input
                                        id={`credit-${line.id}-reason`}
                                        name={`credit-${line.id}-reason`}
                                        maxLength={255}
                                        placeholder="e.g. Scenario reward"
                                        controlSize="lg"
                                        value={value(
                                            form,
                                            `credit-${line.id}-reason`,
                                        )}
                                        onChange={(event) =>
                                            form.change(
                                                `credit-${line.id}-reason`,
                                                event.currentTarget.value,
                                            )
                                        }
                                    />
                                </Field>
                            </div>
                            <Button
                                size="sm"
                                aria-label={line.removeLabel}
                                className="col-start-2 row-start-1 mt-6 h-12 sm:col-start-3"
                                disabled={!!form.pending}
                                busy={
                                    form.pending ===
                                    `remove-credit-line:${line.id}`
                                }
                                onClick={() =>
                                    void form.send(
                                        `remove-credit-line:${line.id}`,
                                    )
                                }
                            >
                                <Icon name="x" className="size-4" />
                            </Button>
                        </li>
                    ))}
                </ul>
                {d.mission.canAddLine && (
                    <Button
                        size="sm"
                        disabled={!!form.pending}
                        busy={form.pending === "add-credit-line"}
                        onClick={() => void form.send("add-credit-line")}
                    >
                        <span className="inline-flex items-center gap-2">
                            <Icon name="plus" className="size-4" />
                            Add credit source
                        </span>
                    </Button>
                )}
                <div className="flex items-baseline justify-between gap-3 border-t border-box-border pt-3 text-sm">
                    <p className="text-muted">Credits from this battle</p>
                    <p className="text-lg font-semibold tabular-nums">
                        {credits > 0 ? "+" : ""}
                        {credits}¢
                    </p>
                </div>
            </div>
            {d.mission.counters.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold">Gang counters</h3>
                    <Counters
                        rows={d.mission.counters}
                        effects={d.mission.counterEffects}
                        steps={false}
                        form={form}
                    />
                </div>
            )}
        </fieldset>
    );
}
