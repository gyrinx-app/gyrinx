import { useId, useState } from "react";
import { Button, CheckboxCard, Field, Input } from "../../ui";

type Option = { value: string; label: string; description: string };
export type AssetSelectionProps = {
    options: Option[];
    label?: string;
    invalid?: boolean;
    selected: string[];
    name: string;
    nameErrors: string[];
};

export function AssetSelection({
    options,
    label = "Assets",
    invalid = false,
    selected: initial,
    name: initialName,
    nameErrors,
}: AssetSelectionProps) {
    const [selected, setSelected] = useState(initial);
    const [name, setName] = useState(initialName);
    const id = useId();
    const canName = selected.length === 1;
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
            <Field
                label="Name in this campaign"
                htmlFor={id}
                errors={nameErrors}
                description={
                    canName
                        ? "Optional. Leave blank to use the asset's own name."
                        : "Select one asset to use a name in this campaign."
                }
            >
                <Input
                    id={id}
                    name="name"
                    value={name}
                    disabled={!canName}
                    maxLength={200}
                    autoComplete="off"
                    onChange={(event) => setName(event.target.value)}
                />
            </Field>
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
        </div>
    );
}
