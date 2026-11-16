import { useId } from "react";
import { Field, Input, NativeSelect } from "../../ui";
import type { Credits, Rewards } from "./types";
import { creditExpression, normalizeRewards, parseRewards } from "./rewardData";

function CreditFields({
    label,
    value,
    onChange,
}: {
    label: string;
    value: Credits;
    onChange: (value: Credits) => void;
}) {
    const prefix = useId();
    return (
        <fieldset className="space-y-2" aria-label={`${label} credits`}>
            <legend className="mb-2 text-sm font-medium">Credits</legend>
            <div className="flex flex-wrap items-end gap-2">
                <div className="w-20">
                    <Field label="Fixed" htmlFor={`${prefix}-fixed`}>
                        <Input
                            aria-label={`${label} fixed credits`}
                            type="number"
                            min="0"
                            step="1"
                            required
                            value={value.fixed}
                            onChange={(event) =>
                                onChange({
                                    ...value,
                                    fixed: Number(event.target.value),
                                })
                            }
                        />
                    </Field>
                </div>
                <div className="flex items-end gap-2">
                    <span className="pb-2 text-muted" aria-hidden="true">
                        +
                    </span>
                    {value.dice && (
                        <div className="w-14">
                            <Field label="Dice" htmlFor={`${prefix}-count`}>
                                <Input
                                    aria-label={`${label} dice count`}
                                    type="number"
                                    min="1"
                                    step="1"
                                    required
                                    value={value.dice.count}
                                    onChange={(event) =>
                                        onChange({
                                            ...value,
                                            dice: {
                                                ...value.dice!,
                                                count: Number(
                                                    event.target.value,
                                                ),
                                            },
                                        })
                                    }
                                />
                            </Field>
                        </div>
                    )}
                    <div className="w-28">
                        <Field label="Die" htmlFor={`${prefix}-dice`}>
                            <NativeSelect
                                aria-label={`${label} die type`}
                                value={value.dice?.sides ?? ""}
                                onChange={(event) =>
                                    onChange({
                                        ...value,
                                        dice: event.target.value
                                            ? {
                                                  count: value.dice?.count ?? 1,
                                                  sides: Number(
                                                      event.target.value,
                                                  ),
                                                  multiplier:
                                                      value.dice?.multiplier ??
                                                      1,
                                              }
                                            : null,
                                    })
                                }
                            >
                                <option value="">No dice</option>
                                <option value="3">D3</option>
                                <option value="6">D6</option>
                            </NativeSelect>
                        </Field>
                    </div>
                    {value.dice && (
                        <>
                            <span
                                className="pb-2 text-muted"
                                aria-hidden="true"
                            >
                                ×
                            </span>
                            <div className="w-20">
                                <Field
                                    label="Multiplier"
                                    htmlFor={`${prefix}-multiplier`}
                                >
                                    <Input
                                        aria-label={`${label} multiplier`}
                                        type="number"
                                        min="1"
                                        step="1"
                                        required
                                        value={value.dice.multiplier}
                                        onChange={(event) =>
                                            onChange({
                                                ...value,
                                                dice: {
                                                    ...value.dice!,
                                                    multiplier: Number(
                                                        event.target.value,
                                                    ),
                                                },
                                            })
                                        }
                                    />
                                </Field>
                            </div>
                        </>
                    )}
                </div>
            </div>
            <output
                aria-label={`${label} credit expression`}
                className="block text-sm tabular-nums"
            >
                {creditExpression(value)}
            </output>
        </fieldset>
    );
}
export function RewardSettings({
    value,
    onChange,
}: {
    value: string | Rewards;
    onChange: (value: string) => void;
}) {
    const settings =
        typeof value === "string"
            ? parseRewards(value)
            : normalizeRewards(value);
    const save = (next: Rewards) => onChange(JSON.stringify(next));
    return (
        <div className="space-y-5">
            <p className="text-sm text-muted">
                Multiply the dice total, then add the fixed credits.
            </p>
            {(["win", "draw", "loss"] as const).map((outcome) => {
                const label = outcome[0].toUpperCase() + outcome.slice(1);
                const reward = settings[outcome];
                return (
                    <fieldset
                        key={outcome}
                        className="space-y-3 border-t border-box-border pt-3"
                    >
                        <legend className="font-medium">{label} reward</legend>
                        <CreditFields
                            label={label}
                            value={reward.credits}
                            onChange={(credits) =>
                                save({
                                    ...settings,
                                    [outcome]: { ...reward, credits },
                                })
                            }
                        />
                        <div className="max-w-28">
                            <Field
                                label="Reputation"
                                htmlFor={`${outcome}-reputation`}
                            >
                                <Input
                                    aria-label={`${label} reputation`}
                                    type="number"
                                    step="1"
                                    required
                                    value={reward.reputation}
                                    onChange={(event) =>
                                        save({
                                            ...settings,
                                            [outcome]: {
                                                ...reward,
                                                reputation: Number(
                                                    event.target.value,
                                                ),
                                            },
                                        })
                                    }
                                />
                            </Field>
                        </div>
                    </fieldset>
                );
            })}
            <fieldset className="space-y-3 border-t border-box-border pt-3">
                <legend className="font-medium">Phase entry</legend>
                <CreditFields
                    label="Phase entry"
                    value={settings.entry_credits}
                    onChange={(credits) =>
                        save({ ...settings, entry_credits: credits })
                    }
                />
            </fieldset>
        </div>
    );
}
