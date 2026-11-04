import { Button, Field, Icon, NativeSelect } from "../ui";

export type SideJobSet = {
    key: string;
    name: string;
    label: string;
    entries: { roll: number; name: string }[];
};

export function SideJobFields({
    picks,
    sets,
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
                const key = keys[index];
                const id = `${prefix}-${key}`;
                return (
                    <fieldset key={key} className="space-y-3">
                        <legend className="mb-2 text-sm font-semibold">
                            Side job {index + 1}
                        </legend>
                        <Field
                            label="Side job set"
                            htmlFor={`${id}-set`}
                            errors={errors[`${key}_set`]}
                        >
                            <NativeSelect
                                id={`${id}-set`}
                                name={submitNames ? `${key}_set` : undefined}
                                aria-label={`Side job ${index + 1} set`}
                                disabled={disabled}
                                value={set?.key ?? pick}
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
                                <option value="leave">Leave out</option>
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
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                disabled={disabled}
                                aria-label={`Remove side job ${index + 1}`}
                                onClick={() =>
                                    onChange(
                                        picks.filter((_, at) => at !== index),
                                    )
                                }
                            >
                                <Icon name="trash-2" /> Remove side job
                            </Button>
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
