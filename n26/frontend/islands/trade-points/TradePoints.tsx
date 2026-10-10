import { useState } from "react";
import {
    Button,
    Field,
    FormActions,
    Input,
    TickList,
    TickListGroup,
    TickListOption,
} from "../../ui";

export type TradePointsOption = {
    key: string;
    name: string;
    points: number;
};

export type TradePointsGroup = {
    name: string;
    options: TradePointsOption[];
};

export type TradePointsProps = {
    amountLabel: string;
    amountDescription?: string;
    emptyMessage: string;
    groups: TradePointsGroup[];
};

export function TradePoints({
    amountLabel,
    amountDescription,
    emptyMessage,
    groups,
}: TradePointsProps) {
    const [brought, setBrought] = useState("");
    const [checked, setChecked] = useState<Record<string, boolean>>({});
    const overridden = brought.trim() !== "";
    const added = groups.reduce(
        (sum, group) =>
            sum +
            group.options.reduce(
                (groupSum, option) =>
                    groupSum + (checked[option.key] ? option.points : 0),
                0,
            ),
        0,
    );

    return (
        <div className="space-y-5">
            {groups.length > 0 ? (
                <fieldset
                    className="min-w-0 border-0 p-0"
                    disabled={overridden}
                >
                    <TickList>
                        {groups.map((group) => (
                            <TickListGroup key={group.name} name={group.name}>
                                {group.options.map((option) => (
                                    <TickListOption
                                        key={option.key}
                                        name="visiting"
                                        value={option.key}
                                        label={option.name}
                                        checked={checked[option.key] ?? false}
                                        disabled={overridden}
                                        onChange={(isChecked) =>
                                            setChecked((current) => ({
                                                ...current,
                                                [option.key]: isChecked,
                                            }))
                                        }
                                    />
                                ))}
                            </TickListGroup>
                        ))}
                    </TickList>
                </fieldset>
            ) : (
                <p className="text-sm text-muted">{emptyMessage}</p>
            )}
            <div className="max-w-xs">
                <Field
                    label={amountLabel}
                    description={amountDescription}
                    htmlFor="brought"
                >
                    <Input
                        id="brought"
                        name="brought"
                        type="number"
                        min={0}
                        max={999}
                        inputMode="numeric"
                        value={brought}
                        onChange={(event) => setBrought(event.target.value)}
                    />
                </Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-box-border pt-4">
                {groups.length > 0 && !overridden && (
                    <p
                        className="text-base text-ink-900 dark:text-ink-100"
                        aria-live="polite"
                    >
                        Total from selected models:{" "}
                        <span className="font-semibold tabular-nums">
                            {added}
                        </span>{" "}
                        TP
                    </p>
                )}
                <FormActions className="ml-auto">
                    <Button type="submit" size="sm" variant="primary">
                        Start visit
                    </Button>
                </FormActions>
            </div>
        </div>
    );
}
