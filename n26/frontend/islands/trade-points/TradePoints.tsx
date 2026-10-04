import { useState } from "react";
import {
    Button,
    Field,
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

    return (
        <>
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
