import { useState } from "react";
import cotton from "../../generated/cotton.json";
import { Button, Field, Input } from "../../ui";

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
    emptyMessage: string;
    groups: TradePointsGroup[];
};

export function TradePoints({
    amountLabel,
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
    const recipe = cotton.tickList;

    return (
        <>
            {groups.length > 0 ? (
                <fieldset
                    className="min-w-0 border-0 p-0"
                    disabled={overridden}
                >
                    <div className={recipe.root}>
                        {groups.map((group) => (
                            <fieldset key={group.name}>
                                <legend className={recipe.legend}>
                                    {group.name}
                                </legend>
                                <div className={recipe.options}>
                                    {group.options.map((option) => (
                                        <label
                                            key={option.key}
                                            className={recipe.label}
                                        >
                                            <input
                                                type="checkbox"
                                                name="visiting"
                                                value={option.key}
                                                checked={
                                                    checked[option.key] ?? false
                                                }
                                                disabled={overridden}
                                                className={recipe.input}
                                                onChange={(event) =>
                                                    setChecked((current) => ({
                                                        ...current,
                                                        [option.key]:
                                                            event.target
                                                                .checked,
                                                    }))
                                                }
                                            />
                                            <span className={recipe.text}>
                                                <span className={recipe.name}>
                                                    {option.name}
                                                </span>
                                            </span>
                                        </label>
                                    ))}
                                </div>
                            </fieldset>
                        ))}
                    </div>
                </fieldset>
            ) : (
                <p className="text-sm text-muted">{emptyMessage}</p>
            )}
            <Field label={amountLabel} htmlFor="brought">
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
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <Button type="submit" size="sm" variant="primary">
                    Start TP visit
                </Button>
                {groups.length > 0 && !overridden && (
                    <p className="text-sm text-muted">
                        Selected models add{" "}
                        <span className="font-medium tabular-nums text-ink-900 dark:text-ink-100">
                            {added}
                        </span>{" "}
                        TP
                    </p>
                )}
            </div>
        </>
    );
}
