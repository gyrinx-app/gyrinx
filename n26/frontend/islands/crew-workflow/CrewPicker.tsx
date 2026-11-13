import { useId, useState } from "react";
import {
    Callout,
    CheckboxCard,
    CheckboxCardItem,
    Field,
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

function allowed(value: string | undefined) {
    return !!value && value.toLowerCase() !== "false";
}

export type CrewPickerProps = {
    models: CrewModel[];
    values: Record<string, string>;
    errors: Record<string, string[]>;
    onChange: (name: string, value: string) => void;
};

export function CrewPicker({
    models,
    values,
    errors,
    onChange,
}: CrewPickerProps) {
    const headingId = useId();
    const [query, setQuery] = useState("");
    const [lastRoles, setLastRoles] = useState<Record<string, string>>({});
    const [repairAllow] = useState(
        () =>
            new Set(
                models
                    .filter(
                        (model) =>
                            model.mayOverride &&
                            values[model.role.name] &&
                            values[model.role.name] !== "out" &&
                            !allowed(values[model.override.name]),
                    )
                    .map((model) => model.id),
            ),
    );
    const selections = Object.fromEntries(
        models.map((model) => [
            model.id,
            {
                selected:
                    !!values[model.role.name] &&
                    values[model.role.name] !== "out",
                role:
                    values[model.role.name] === "out"
                        ? (lastRoles[model.id] ?? "starting")
                        : values[model.role.name],
                card: values[model.card.name] ?? "",
            },
        ]),
    );
    function update(
        id: string,
        change: { selected?: boolean; role?: string; card?: string },
    ) {
        const model = models.find((model) => model.id === id)!;
        if (change.selected !== undefined) {
            if (model.mayOverride || !change.selected)
                onChange(model.override.name, change.selected ? "on" : "");
            if (!change.selected)
                setLastRoles((previous) => ({
                    ...previous,
                    [id]: selections[id].role,
                }));
            onChange(
                model.role.name,
                change.selected ? (lastRoles[id] ?? "starting") : "out",
            );
        }
        if (change.role !== undefined) onChange(model.role.name, change.role);
        if (change.card !== undefined) onChange(model.card.name, change.card);
    }
    const wanted = query.trim().toLowerCase();
    const shown = models.filter((model) => model.search.includes(wanted));
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
                            value={values[model.role.name] ?? ""}
                        />
                        <input
                            type="hidden"
                            name={model.card.name}
                            value={value.card}
                        />
                        {(!model.mayOverride ||
                            !repairAllow.has(model.id) ||
                            !value.selected ||
                            !allowed(values[model.override.name]) ||
                            !shown.some((item) => item.id === model.id)) && (
                            <input
                                type="hidden"
                                name={model.override.name}
                                value={values[model.override.name] ?? ""}
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
                                        All equipment
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
                                        {(
                                            errors[model.override.name] ?? []
                                        ).map((error) => (
                                            <p
                                                key={error}
                                                role="alert"
                                                className="mt-2 text-sm text-red-700 dark:text-red-300"
                                            >
                                                {error}
                                            </p>
                                        ))}
                                        {(errors[model.role.name] ?? [])
                                            .length > 0 && (
                                            <div
                                                id={roleErrorId}
                                                role="alert"
                                                className="mt-2 text-sm text-red-700 dark:text-red-300"
                                            >
                                                {(
                                                    errors[model.role.name] ??
                                                    []
                                                ).join(" ")}
                                            </div>
                                        )}
                                        {(errors[model.card.name] ?? [])
                                            .length > 0 && (
                                            <div
                                                id={cardErrorId}
                                                role="alert"
                                                className="mt-2 text-sm text-red-700 dark:text-red-300"
                                            >
                                                {(
                                                    errors[model.card.name] ??
                                                    []
                                                ).join(" ")}
                                            </div>
                                        )}
                                    </>
                                }
                            >
                                <div className="space-y-3">
                                    <Field
                                        label="Starting crew or reinforcement"
                                        htmlFor={model.role.id}
                                    >
                                        <NativeSelect
                                            id={model.role.id}
                                            aria-label={`Starting crew or reinforcement for ${model.name}`}
                                            aria-invalid={
                                                (errors[model.role.name] ?? [])
                                                    .length > 0 || undefined
                                            }
                                            aria-describedby={
                                                (errors[model.role.name] ?? [])
                                                    .length
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
                                            {!model.role.choices.some(
                                                (choice) =>
                                                    choice.value ===
                                                        value.role &&
                                                    choice.value !== "out",
                                            ) && (
                                                <option
                                                    value={value.role}
                                                    disabled
                                                >
                                                    Select a crew role
                                                </option>
                                            )}
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
                                                (errors[model.card.name] ?? [])
                                                    .length > 0 || undefined
                                            }
                                            aria-describedby={
                                                (errors[model.card.name] ?? [])
                                                    .length
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
                                    {model.mayOverride &&
                                        repairAllow.has(model.id) && (
                                            <CheckboxCardItem
                                                name={model.override.name}
                                                value={
                                                    values[
                                                        model.override.name
                                                    ] || "on"
                                                }
                                                disabled={!included}
                                                label="Allow for this battle"
                                                checked={allowed(
                                                    values[model.override.name],
                                                )}
                                                onCheckedChange={(checked) =>
                                                    onChange(
                                                        model.override.name,
                                                        checked ? "on" : "",
                                                    )
                                                }
                                            />
                                        )}
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
        </div>
    );
}
