import { useId, useState } from "react";
import { Button, CheckboxCard, Field, Input } from "../../ui";

type Option = {
    value: string;
    label: string;
    description: string;
    name?: string;
    nameErrors?: string[];
};
export type AssetSelectionProps = {
    options: Option[];
    label?: string;
    invalid?: boolean;
    selected: string[];
};

export function AssetSelection({
    options,
    label = "Assets",
    invalid = false,
    selected: initial,
}: AssetSelectionProps) {
    const [selected, setSelected] = useState(initial);
    const [names, setNames] = useState<Record<string, string>>(
        Object.fromEntries(
            options.map((item) => [item.value, item.name || ""]),
        ),
    );
    const id = useId();
    const selectedOptions = options.filter((item) =>
        selected.includes(item.value),
    );
    function choose(value: string, checked: boolean) {
        setSelected((values) =>
            checked
                ? [...values, value]
                : values.filter((item) => item !== value),
        );
    }
    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
                <Button
                    type="button"
                    size="sm"
                    onClick={() =>
                        setSelected(options.map((item) => item.value))
                    }
                >
                    Select all
                </Button>
                <Button type="button" size="sm" onClick={() => setSelected([])}>
                    Clear
                </Button>
                <p role="status" className="text-sm text-muted">
                    {selected.length} selected
                </p>
            </div>
            <fieldset
                aria-describedby="campaign-assets-help campaign-assets-errors"
                aria-invalid={invalid || undefined}
            >
                <legend className="sr-only">{label}</legend>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {options.map((item) => (
                        <div key={item.value}>
                            <CheckboxCard
                                checked={selected.includes(item.value)}
                                onCheckedChange={(checked) =>
                                    choose(item.value, checked)
                                }
                                label={item.label}
                                description={item.description}
                            />
                            {selected.includes(item.value) && (
                                <input
                                    type="hidden"
                                    name="asset"
                                    value={item.value}
                                />
                            )}
                        </div>
                    ))}
                </div>
            </fieldset>
            {selectedOptions.length > 1 && (
                <p className="text-sm text-muted">
                    When you select several assets, they keep their catalogue
                    names. Select one asset to give it a custom name in this
                    campaign.
                </p>
            )}
            {selectedOptions.length === 1 &&
                selectedOptions.map((item) => (
                    <Field
                        key={item.value}
                        label="Name in this campaign (optional)"
                        htmlFor={`${id}-${item.value}`}
                        description="Leave blank to use the catalogue name."
                        errors={item.nameErrors}
                    >
                        <Input
                            id={`${id}-${item.value}`}
                            name={`name_${item.value}`}
                            placeholder={item.label}
                            value={names[item.value] || ""}
                            maxLength={200}
                            autoComplete="off"
                            onChange={(event) =>
                                setNames((values) => ({
                                    ...values,
                                    [item.value]: event.target.value,
                                }))
                            }
                        />
                    </Field>
                ))}
        </div>
    );
}
