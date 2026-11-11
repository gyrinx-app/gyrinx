import {
    Badge,
    Button,
    Field,
    HelpPopover,
    Input,
    NativeSelect,
    Textarea,
} from "../../ui";
import { Counters } from "./Counters";
import { value, type ReportModel } from "./types";
import type { Draft } from "./useReportDraft";
export function ModelResults({
    model,
    form,
}: {
    model: ReportModel;
    form: Draft;
}) {
    const p = model.prefix;
    return (
        <fieldset
            id={`result-${model.id}`}
            className="min-w-0 scroll-mt-24 border border-box-border bg-surface p-4 sm:p-5"
        >
            <legend className="sr-only">{model.name}</legend>
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <div className="min-w-0">
                    <h3 className="flex min-w-0 flex-wrap items-center gap-2 text-base font-semibold">
                        <span className="min-w-0">{model.name}</span>
                        <Badge
                            color={
                                model.statusColour as "ink" | "amber" | "red"
                            }
                        >
                            <span className="sr-only">Status: </span>
                            {model.statusLabel}
                        </Badge>
                    </h3>
                    {model.profileName && (
                        <p className="mt-1 text-sm text-muted">
                            {model.profileName}
                        </p>
                    )}
                    {model.ownedBy && (
                        <p className="mt-1 text-sm text-muted">
                            Owned by {model.ownedBy}
                        </p>
                    )}
                </div>
                <label
                    className="flex min-h-11 items-center gap-3 text-sm font-medium"
                    htmlFor={`${p}-participated`}
                >
                    <input
                        id={`${p}-participated`}
                        name={`${p}-participated`}
                        type="checkbox"
                        className="size-5 shrink-0 accent-[var(--color-accent)]"
                        checked={value(form, `${p}-participated`) === "on"}
                        onChange={(event) =>
                            form.change(
                                `${p}-participated`,
                                event.currentTarget.checked ? "on" : [],
                            )
                        }
                        aria-label={`${model.name} took part`}
                    />
                    Took part
                </label>
            </div>
            {form.showErrors && model.errors.length > 0 && (
                <ul
                    id={`${p}-errors`}
                    className="mt-3 list-disc space-y-1 pl-5 text-sm text-red-700 dark:text-red-300"
                >
                    {model.errors.map((error) => (
                        <li key={error}>{error}</li>
                    ))}
                </ul>
            )}
            <div className="mt-4 max-w-xl space-y-4">
                <div className="space-y-4">
                    <Field
                        label="XP gained"
                        htmlFor={`${p}-xp`}
                        description={
                            model.xpAvailable
                                ? `Current XP: ${model.xpBefore}`
                                : undefined
                        }
                    >
                        {model.xpAvailable ? (
                            <Input
                                id={`${p}-xp`}
                                name={`${p}-xp`}
                                type="number"
                                min="0"
                                inputMode="numeric"
                                controlSize="lg"
                                value={value(form, `${p}-xp`)}
                                onChange={(event) =>
                                    form.change(
                                        `${p}-xp`,
                                        event.currentTarget.value,
                                    )
                                }
                            />
                        ) : (
                            <HelpPopover
                                label={`Why ${model.name} cannot take XP`}
                            >
                                <p>{model.xpHelp}</p>
                            </HelpPopover>
                        )}
                    </Field>
                    <div id={`${p}-xp-help`}>
                        {form.showErrors && model.errors.length > 0 && (
                            <a
                                href={`#${p}-errors`}
                                className="block text-xs text-red-700 underline dark:text-red-300"
                            >
                                Check this model's results
                            </a>
                        )}
                    </div>
                    {model.counters.length > 0 && (
                        <div className="space-y-1.5">
                            <h4 className="text-sm font-medium">Counters</h4>
                            <Counters
                                rows={model.counters}
                                effects={model.counterEffects}
                                steps
                                form={form}
                            />
                        </div>
                    )}
                </div>
                <div className="space-y-4">
                    {model.effects.map((effect) => (
                        <div key={effect.id} className="space-y-3">
                            {effect.retainedChoices.length > 0 && (
                                <div className="space-y-2 text-sm">
                                    <p>
                                        Some saved choices no longer fit this
                                        result. Reset its choices, then choose
                                        again.
                                    </p>
                                    <Button
                                        size="sm"
                                        busy={
                                            form.pending ===
                                            `clear-choices:${effect.id}`
                                        }
                                        onClick={() =>
                                            void form.send(
                                                `clear-choices:${effect.id}`,
                                            )
                                        }
                                        disabled={!!form.pending}
                                    >
                                        Reset choices
                                    </Button>
                                </div>
                            )}
                            <Field
                                label={effect.label}
                                htmlFor={`effect-${effect.id}-pick`}
                            >
                                <NativeSelect
                                    id={`effect-${effect.id}-pick`}
                                    name={`effect-${effect.id}-pick`}
                                    controlSize="lg"
                                    value={value(
                                        form,
                                        `effect-${effect.id}-pick`,
                                    )}
                                    onChange={(event) =>
                                        form.change(
                                            `effect-${effect.id}-pick`,
                                            event.currentTarget.value,
                                        )
                                    }
                                >
                                    <option value="">Choose a result</option>
                                    {effect.retainedOption && (
                                        <option value={effect.selected}>
                                            {effect.name}
                                        </option>
                                    )}
                                    {model.effectGroups.map((group) => (
                                        <optgroup
                                            key={group.label}
                                            label={group.label}
                                        >
                                            {group.options.map((option) => (
                                                <option
                                                    key={option.value}
                                                    value={option.value}
                                                >
                                                    {option.label}
                                                </option>
                                            ))}
                                        </optgroup>
                                    ))}
                                </NativeSelect>
                            </Field>
                            {effect.questions.map((question, index) => (
                                <Field
                                    key={question.key}
                                    label={question.label}
                                    htmlFor={`effect-${effect.id}-choice-${index + 1}`}
                                >
                                    <NativeSelect
                                        id={`effect-${effect.id}-choice-${index + 1}`}
                                        name={`effect-${effect.id}-choice-${question.key}`}
                                        controlSize="lg"
                                        multiple={question.multiple}
                                        value={
                                            question.multiple
                                                ? form.draft.getAll(
                                                      `effect-${effect.id}-choice-${question.key}`,
                                                  )
                                                : value(
                                                      form,
                                                      `effect-${effect.id}-choice-${question.key}`,
                                                  )
                                        }
                                        onChange={(event) =>
                                            form.change(
                                                `effect-${effect.id}-choice-${question.key}`,
                                                [
                                                    ...event.currentTarget
                                                        .selectedOptions,
                                                ].map((option) => option.value),
                                            )
                                        }
                                    >
                                        {!question.multiple && (
                                            <option value="">
                                                {question.required
                                                    ? "Choose an option"
                                                    : "None"}
                                            </option>
                                        )}
                                        {question.options.map((option) => (
                                            <option
                                                key={option.value}
                                                value={option.value}
                                            >
                                                {option.label}
                                            </option>
                                        ))}
                                    </NativeSelect>
                                </Field>
                            ))}
                            <Button
                                size="sm"
                                variant="ghost"
                                aria-label={`Remove ${effect.label}`}
                                disabled={!!form.pending}
                                busy={
                                    form.pending ===
                                    `remove-effect:${effect.id}`
                                }
                                onClick={() =>
                                    void form.send(`remove-effect:${effect.id}`)
                                }
                            >
                                Remove
                            </Button>
                        </div>
                    ))}
                    {model.addEffectLabel ? (
                        <Button
                            size="sm"
                            disabled={!!form.pending}
                            busy={form.pending === `add-effect:${model.id}`}
                            onClick={() =>
                                void form.send(`add-effect:${model.id}`)
                            }
                        >
                            {model.addEffectLabel}
                        </Button>
                    ) : (
                        <p className="text-sm text-muted">
                            This model has no injury or damage table.
                        </p>
                    )}
                    <Field
                        label="Final status"
                        htmlFor={`${p}-status`}
                        errors={
                            model.statusConflict ? [model.statusConflict] : []
                        }
                    >
                        <NativeSelect
                            id={`${p}-status`}
                            name={`${p}-status`}
                            controlSize="lg"
                            value={value(form, `${p}-status`)}
                            onChange={(event) =>
                                form.change(
                                    `${p}-status`,
                                    event.currentTarget.value,
                                )
                            }
                        >
                            <option value="">
                                Set from its current status and results
                            </option>
                            {model.statusOptions.map((option) => (
                                <option key={option.value} value={option.value}>
                                    {option.label}
                                </option>
                            ))}
                        </NativeSelect>
                    </Field>
                    {!model.statusConflict && model.statusChanges && (
                        <p className="flex flex-wrap items-center gap-2 text-sm">
                            After this battle:{" "}
                            <Badge
                                color={
                                    model.finalStatusColour as
                                        "ink" | "amber" | "red"
                                }
                            >
                                {model.finalStatusLabel}
                            </Badge>
                        </p>
                    )}
                    {model.equipmentApplies ? (
                        <>
                            <Field
                                label={model.equipmentLabel}
                                htmlFor={`${p}-equipment`}
                            >
                                <NativeSelect
                                    id={`${p}-equipment`}
                                    name={`${p}-equipment`}
                                    controlSize="lg"
                                    value={value(form, `${p}-equipment`)}
                                    onChange={(event) =>
                                        form.change(
                                            `${p}-equipment`,
                                            event.currentTarget.value,
                                        )
                                    }
                                >
                                    <option value="keep">
                                        Leave with the model
                                    </option>
                                    <option value="stash">
                                        Move equipment to the stash
                                    </option>
                                    <option value="lost">
                                        Mark equipment lost
                                    </option>
                                </NativeSelect>
                            </Field>
                            {model.equipmentChanged && (
                                <>
                                    <p className="text-sm">
                                        {model.equipmentDisposition === "stash"
                                            ? "Moves to the stash"
                                            : "Marked lost"}
                                        :{" "}
                                        {model.equipmentNames.join(", ") ||
                                            "No equipment"}
                                        .
                                    </p>
                                    {model.equipmentExclusions.length > 0 && (
                                        <p className="text-sm text-muted">
                                            Stays with the model:{" "}
                                            {model.equipmentExclusions.join(
                                                ", ",
                                            )}
                                            .
                                        </p>
                                    )}
                                </>
                            )}
                            <p className="text-xs text-muted">
                                Equipment moved or marked lost cannot be
                                restored by correcting this report.
                            </p>
                        </>
                    ) : (
                        <p className="text-sm text-muted">
                            You can move equipment or mark it lost only when
                            this model is dead or destroyed.
                        </p>
                    )}
                </div>
            </div>
            <div className="mt-5 space-y-1.5">
                <Field
                    label={model.noteLabel}
                    htmlFor={`${p}-note`}
                    description={model.noteHelp}
                >
                    <Textarea
                        id={`${p}-note`}
                        name={`${p}-note`}
                        maxLength={model.noteLimit}
                        className="min-h-20"
                        value={value(form, `${p}-note`)}
                        onChange={(event) =>
                            form.change(`${p}-note`, event.currentTarget.value)
                        }
                    />
                </Field>
            </div>
        </fieldset>
    );
}
