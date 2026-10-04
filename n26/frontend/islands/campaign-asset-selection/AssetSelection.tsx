import { useId, useState } from "react";
import { Button, Card, CheckboxCard, Input, Table } from "../../ui";

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
    renameLabel?: string;
    itemLabel?: string;
};

export function AssetSelection({
    options,
    label = "Assets",
    invalid = false,
    selected: initial,
    renameLabel = "Optional: Rename assets",
    itemLabel = "Asset",
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
            {selectedOptions.length > 0 && (
                <Card>
                    <details
                        open={
                            selectedOptions.some(
                                (item) => item.nameErrors?.length,
                            ) || undefined
                        }
                    >
                        <summary className="cursor-pointer font-medium">
                            {renameLabel}
                        </summary>
                        <div className="mt-4">
                            <Table>
                                <thead>
                                    <tr>
                                        <th scope="col">{itemLabel}</th>
                                        <th scope="col">Rename to</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {selectedOptions.map((item) => (
                                        <tr key={item.value}>
                                            <th
                                                scope="row"
                                                className="font-normal"
                                            >
                                                {item.label}
                                            </th>
                                            <td className="min-w-48">
                                                <Input
                                                    id={`${id}-${item.value}`}
                                                    aria-label={`Rename ${item.label}`}
                                                    aria-invalid={
                                                        Boolean(
                                                            item.nameErrors
                                                                ?.length,
                                                        ) || undefined
                                                    }
                                                    aria-describedby={
                                                        item.nameErrors?.length
                                                            ? `${id}-${item.value}-errors`
                                                            : undefined
                                                    }
                                                    name={`name_${item.value}`}
                                                    placeholder={item.label}
                                                    value={
                                                        names[item.value] || ""
                                                    }
                                                    maxLength={200}
                                                    autoComplete="off"
                                                    onChange={(event) =>
                                                        setNames((values) => ({
                                                            ...values,
                                                            [item.value]:
                                                                event.target
                                                                    .value,
                                                        }))
                                                    }
                                                />
                                                {Boolean(
                                                    item.nameErrors?.length,
                                                ) && (
                                                    <div
                                                        id={`${id}-${item.value}-errors`}
                                                        className="mt-1 text-sm text-red-700 dark:text-red-400"
                                                    >
                                                        {item.nameErrors!.map(
                                                            (error) => (
                                                                <p key={error}>
                                                                    {error}
                                                                </p>
                                                            ),
                                                        )}
                                                    </div>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </Table>
                        </div>
                    </details>
                </Card>
            )}
        </div>
    );
}
