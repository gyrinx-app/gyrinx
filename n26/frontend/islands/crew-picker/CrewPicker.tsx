import { useEffect, useId, useRef, useState } from "react";
import {
    Button,
    ButtonLink,
    Callout,
    CheckboxCard,
    Field,
    FormActions,
    NativeSelect,
    SearchBar,
} from "../../ui";

type SelectField = {
    name: string;
    id: string;
    value: string | null;
    errors: string[];
    choices: { value: string; label: string }[];
};

export type CrewModel = {
    id: string;
    name: string;
    profile: string;
    fullRating: number;
    savedSource: string;
    search: string;
    warning: string;
    mayOverride: boolean;
    available: boolean;
    role: SelectField;
    card: SelectField;
    override: { name: string; id: string; value: boolean; errors: string[] };
};

export type CrewPickerProps = {
    models: CrewModel[];
    battleUrl: string;
    revision: number | null;
};

export function CrewPicker({ models, battleUrl, revision }: CrewPickerProps) {
    const headingId = useId();
    const [query, setQuery] = useState("");
    const [selections, setSelections] = useState(() =>
        Object.fromEntries(
            models.map((model) => [
                model.id,
                {
                    selected:
                        !!model.role.value &&
                        model.role.value !== "out" &&
                        (!model.mayOverride || model.override.value),
                    role:
                        model.role.value === "reserve" ? "reserve" : "starting",
                    card: model.card.value ?? "",
                },
            ]),
        ),
    );
    const actions = useRef<HTMLDivElement>(null);
    const wanted = query.trim().toLowerCase();
    const shown = models.filter((model) => model.search.includes(wanted));
    const selected = Object.values(selections).filter(
        (value) => value.selected,
    );
    const starting = selected.filter(
        (value) => value.role === "starting",
    ).length;
    const reserves = selected.length - starting;

    useEffect(() => {
        const element = actions.current;
        if (!element) return;
        const measure = () => {
            document.documentElement.style.setProperty(
                "--n26-battle-actions-height",
                `${element.getBoundingClientRect().height}px`,
            );
        };
        measure();
        const observer = window.ResizeObserver
            ? new ResizeObserver(measure)
            : null;
        observer?.observe(element);
        window.addEventListener("resize", measure);
        return () => {
            observer?.disconnect();
            window.removeEventListener("resize", measure);
            document.documentElement.style.removeProperty(
                "--n26-battle-actions-height",
            );
        };
    }, []);

    function update(id: string, change: Partial<(typeof selections)[string]>) {
        setSelections((previous) => ({
            ...previous,
            [id]: { ...previous[id], ...change },
        }));
    }

    return (
        <div className="space-y-4">
            {/* The Django form requires every model's fields, including models hidden by search. */}
            {models.map((model) => {
                const value = selections[model.id];
                return (
                    <div key={model.id} hidden>
                        <input
                            type="hidden"
                            name={model.role.name}
                            value={value.selected ? value.role : "out"}
                        />
                        <input
                            type="hidden"
                            name={model.card.name}
                            value={value.card}
                        />
                        {value.selected && model.mayOverride && (
                            <input
                                type="hidden"
                                name={model.override.name}
                                value="on"
                            />
                        )}
                    </div>
                );
            })}
            <section aria-labelledby={headingId}>
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <h2 id={headingId} className="text-lg font-semibold">
                        Models
                    </h2>
                    <div className="w-full sm:w-64">
                        <SearchBar
                            label="Find a model"
                            value={query}
                            onChange={setQuery}
                        />
                    </div>
                </div>
                <div className="grid grid-cols-1 items-stretch gap-4 md:auto-rows-fr md:grid-cols-2 xl:grid-cols-3">
                    {shown.map((model) => {
                        const value = selections[model.id];
                        const included = value.selected;
                        const roleErrorId = `${model.role.id}-error`;
                        const cardErrorId = `${model.card.id}-error`;
                        const warningId = `${model.override.id}-warning`;
                        return (
                            <CheckboxCard
                                key={model.id}
                                className="min-w-0"
                                label={model.name}
                                description={model.profile}
                                checkboxLabel={`Select ${model.name}`}
                                checkboxDescribedBy={
                                    model.warning ? warningId : undefined
                                }
                                checked={included}
                                disabled={!model.available && !value.selected}
                                onCheckedChange={(selected) =>
                                    update(model.id, { selected })
                                }
                                meta={
                                    <span className="shrink-0 text-right text-xs tabular-nums text-muted">
                                        Full equipment
                                        <br />
                                        {model.fullRating}¢
                                    </span>
                                }
                                notice={
                                    model.warning && (
                                        <Callout
                                            id={warningId}
                                            className="mt-3"
                                        >
                                            {model.warning}
                                        </Callout>
                                    )
                                }
                                errors={
                                    <>
                                        {model.override.errors.map((error) => (
                                            <p
                                                key={error}
                                                role="alert"
                                                className="mt-2 text-sm text-red-700 dark:text-red-300"
                                            >
                                                {error}
                                            </p>
                                        ))}
                                        {model.role.errors.length > 0 && (
                                            <div
                                                id={roleErrorId}
                                                role="alert"
                                                className="mt-2 text-sm text-red-700 dark:text-red-300"
                                            >
                                                {model.role.errors.join(" ")}
                                            </div>
                                        )}
                                        {model.card.errors.length > 0 && (
                                            <div
                                                id={cardErrorId}
                                                role="alert"
                                                className="mt-2 text-sm text-red-700 dark:text-red-300"
                                            >
                                                {model.card.errors.join(" ")}
                                            </div>
                                        )}
                                    </>
                                }
                            >
                                <div className="space-y-3">
                                    <Field label="Crew" htmlFor={model.role.id}>
                                        <NativeSelect
                                            id={model.role.id}
                                            aria-label={`Crew for ${model.name}`}
                                            aria-invalid={
                                                model.role.errors.length > 0 ||
                                                undefined
                                            }
                                            aria-describedby={
                                                model.role.errors.length
                                                    ? roleErrorId
                                                    : undefined
                                            }
                                            value={value.role}
                                            disabled={!included}
                                            onChange={(event) =>
                                                update(model.id, {
                                                    role: event.target.value,
                                                })
                                            }
                                        >
                                            {model.role.choices
                                                .filter(
                                                    (choice) =>
                                                        choice.value !== "out",
                                                )
                                                .map((choice) => (
                                                    <option
                                                        key={choice.value}
                                                        value={choice.value}
                                                    >
                                                        {choice.label}
                                                    </option>
                                                ))}
                                        </NativeSelect>
                                    </Field>
                                    <Field
                                        label="Equipment set"
                                        htmlFor={model.card.id}
                                    >
                                        <NativeSelect
                                            id={model.card.id}
                                            aria-label={`Equipment set for ${model.name}`}
                                            aria-invalid={
                                                model.card.errors.length > 0 ||
                                                undefined
                                            }
                                            aria-describedby={
                                                model.card.errors.length
                                                    ? cardErrorId
                                                    : undefined
                                            }
                                            value={value.card}
                                            disabled={!included}
                                            onChange={(event) =>
                                                update(model.id, {
                                                    card: event.target.value,
                                                })
                                            }
                                        >
                                            {!model.card.choices.some(
                                                (choice) =>
                                                    choice.value === value.card,
                                            ) && (
                                                <option
                                                    value={value.card}
                                                    disabled
                                                >
                                                    Select an equipment set
                                                </option>
                                            )}
                                            {model.card.choices.map(
                                                (choice) => (
                                                    <option
                                                        key={choice.value}
                                                        value={choice.value}
                                                    >
                                                        {choice.label}
                                                    </option>
                                                ),
                                            )}
                                        </NativeSelect>
                                    </Field>
                                    {model.savedSource && (
                                        <p className="text-xs text-muted">
                                            {model.savedSource}
                                        </p>
                                    )}
                                </div>
                            </CheckboxCard>
                        );
                    })}
                </div>
                {!shown.length && (
                    <p className="py-4 text-sm text-muted">
                        {models.length
                            ? "No models match your search."
                            : "No models in this gang yet."}
                    </p>
                )}
            </section>
            <p className="text-xs text-muted">
                A saved crew keeps its equipment selection. To use an edited
                equipment set, select it again from the list.
            </p>
            <div
                ref={actions}
                className="n26-battle-actions"
                data-battle-actions
                aria-label="Save crew"
            >
                <div className="n26-site-container flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm" role="status" aria-live="polite">
                        <p className="font-semibold">
                            {selected.length}{" "}
                            {selected.length === 1 ? "model" : "models"}
                        </p>
                        <p className="text-xs text-muted">
                            {starting} starting · {reserves}{" "}
                            {reserves === 1
                                ? "reinforcement"
                                : "reinforcements"}
                            {revision !== null && ` · Revision ${revision}`}
                        </p>
                    </div>
                    <FormActions className="w-full sm:w-auto">
                        <ButtonLink href={battleUrl} variant="ghost">
                            Back
                        </ButtonLink>
                        <Button type="submit" name="action" value="draft">
                            Save draft
                        </Button>
                        <Button
                            type="submit"
                            name="action"
                            value="save"
                            variant="success"
                        >
                            Save crew
                        </Button>
                    </FormActions>
                </div>
            </div>
        </div>
    );
}
