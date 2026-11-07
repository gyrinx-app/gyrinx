import { Button, Field, Icon, NativeSelect, PickLegend } from "../ui";

export type SideJobSet = {
    key: string;
    name: string;
    label: string;
    entries: { roll: number; name: string }[];
};

export function SideJobFields({
    picks,
    sets,
    referencedSets = [],
    keys,
    limit,
    onChange,
    disabled = false,
    prefix,
    errors = {},
    submitNames = false,
}: {
    picks: string[];
    sets: SideJobSet[];
    referencedSets?: SideJobSet[];
    keys: string[];
    limit: number;
    onChange: (picks: string[]) => void;
    disabled?: boolean;
    prefix: string;
    errors?: Record<string, string[]>;
    submitNames?: boolean;
}) {
    return (
        <div className="space-y-4">
            {picks.map((pick, index) => {
                const set = sets.find(
                    (each) =>
                        pick === each.key || pick.startsWith(`${each.key}-`),
                );
                const unavailable = !set
                    ? referencedSets.find(
                          (each) =>
                              pick === each.key ||
                              pick.startsWith(`${each.key}-`),
                      )
                    : undefined;
                const key = keys[index];
                const id = `${prefix}-${key}`;
                return (
                    <fieldset key={key} className="space-y-3">
                        <PickLegend
                            name={`Side job ${index + 1}`}
                            caption=""
                            tone="muted"
                        />
                        <Field
                            label="Side job set"
                            htmlFor={`${id}-set`}
                            errors={errors[`${key}_set`]}
                            description={
                                unavailable
                                    ? "Select an available set to generate this side job again."
                                    : undefined
                            }
                        >
                            <NativeSelect
                                id={`${id}-set`}
                                name={submitNames ? `${key}_set` : undefined}
                                aria-label={`Side job ${index + 1} set`}
                                disabled={disabled}
                                value={set?.key ?? unavailable?.key ?? pick}
                                onChange={(event) =>
                                    onChange(
                                        picks.map((value, at) =>
                                            at === index
                                                ? event.target.value
                                                : value,
                                        ),
                                    )
                                }
                            >
                                <option value="">Choose a side job set</option>
                                {unavailable && (
                                    <option value={unavailable.key} disabled>
                                        {unavailable.label} (unavailable)
                                    </option>
                                )}
                                {sets.map((each) => (
                                    <option key={each.key} value={each.key}>
                                        {each.label}
                                    </option>
                                ))}
                            </NativeSelect>
                        </Field>
                        <Field
                            label="Side job"
                            htmlFor={id}
                            errors={errors[`${key}_pick`]}
                        >
                            <NativeSelect
                                id={id}
                                name={submitNames ? `${key}_pick` : undefined}
                                aria-label={`Side job ${index + 1}`}
                                disabled={disabled || !set}
                                value={set ? pick : ""}
                                onChange={(event) =>
                                    onChange(
                                        picks.map((value, at) =>
                                            at === index
                                                ? event.target.value
                                                : value,
                                        ),
                                    )
                                }
                            >
                                {set ? (
                                    <>
                                        <option value={set.key}>
                                            Roll a D6
                                        </option>
                                        {set.entries.map((entry) => (
                                            <option
                                                key={entry.roll}
                                                value={`${set.key}-${entry.roll}`}
                                            >
                                                {entry.roll}. {entry.name}
                                            </option>
                                        ))}
                                    </>
                                ) : (
                                    <option value="">
                                        Choose a side job set first
                                    </option>
                                )}
                            </NativeSelect>
                        </Field>
                        {index > 0 && (
                            <div className="flex justify-end">
                                <Button
                                    type="button"
                                    variant="text"
                                    size="xs"
                                    className="inline-flex items-center gap-1.5 whitespace-nowrap"
                                    disabled={disabled}
                                    aria-label={`Remove side job ${index + 1}`}
                                    onClick={() =>
                                        onChange(
                                            picks.filter(
                                                (_, at) => at !== index,
                                            ),
                                        )
                                    }
                                >
                                    <Icon name="trash-2" className="size-3.5" />{" "}
                                    Remove side job
                                </Button>
                            </div>
                        )}
                    </fieldset>
                );
            })}
            {picks.length < limit && (
                <Button
                    type="button"
                    size="sm"
                    disabled={disabled}
                    onClick={() => onChange([...picks, ""])}
                >
                    + Add side job
                </Button>
            )}
        </div>
    );
}
