import { Field, Input, NativeSelect } from "../../ui";
import type { Credits, Reward, Rewards } from "./types";

const emptyCredits = (): Credits => ({ fixed: 0, dice: null });
const emptyReward = (): Reward => ({ credits: emptyCredits(), reputation: 0 });
function parse(value: string): Rewards {
    const blank = {
        win: emptyReward(),
        draw: emptyReward(),
        loss: emptyReward(),
        entry_credits: emptyCredits(),
    };
    const object = (item: unknown): item is Record<string, unknown> =>
        typeof item === "object" && item !== null;
    function credits(item: unknown): Credits {
        if (!object(item) || typeof item.fixed !== "number")
            return emptyCredits();
        const dice = item.dice;
        return {
            fixed: item.fixed,
            dice:
                object(dice) &&
                typeof dice.count === "number" &&
                typeof dice.sides === "number" &&
                typeof dice.multiplier === "number"
                    ? {
                          count: dice.count,
                          sides: dice.sides,
                          multiplier: dice.multiplier,
                      }
                    : null,
        };
    }
    function reward(item: unknown): Reward {
        return object(item)
            ? {
                  credits: credits(item.credits),
                  reputation:
                      typeof item.reputation === "number" ? item.reputation : 0,
              }
            : emptyReward();
    }
    try {
        const parsed: unknown = JSON.parse(value);
        if (!object(parsed)) return blank;
        return {
            win: reward(parsed.win),
            draw: reward(parsed.draw),
            loss: reward(parsed.loss),
            entry_credits: credits(parsed.entry_credits),
        };
    } catch {
        return blank;
    }
}
function CreditFields({
    label,
    value,
    onChange,
}: {
    label: string;
    value: Credits;
    onChange: (value: Credits) => void;
}) {
    const prefix = label.toLowerCase().replaceAll(" ", "-");
    return (
        <div className="grid grid-cols-2 gap-3">
            <Field label={`${label} fixed credits`} htmlFor={`${prefix}-fixed`}>
                <Input
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
            <Field label={`${label} dice`} htmlFor={`${prefix}-dice`}>
                <NativeSelect
                    value={value.dice?.sides ?? ""}
                    onChange={(event) =>
                        onChange({
                            ...value,
                            dice: event.target.value
                                ? {
                                      count: value.dice?.count ?? 1,
                                      sides: Number(event.target.value),
                                      multiplier: value.dice?.multiplier ?? 1,
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
            {value.dice && (
                <>
                    <Field
                        label={`${label} dice count`}
                        htmlFor={`${prefix}-count`}
                    >
                        <Input
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
                                        count: Number(event.target.value),
                                    },
                                })
                            }
                        />
                    </Field>
                    <Field
                        label={`${label} multiplier`}
                        htmlFor={`${prefix}-multiplier`}
                    >
                        <Input
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
                                        multiplier: Number(event.target.value),
                                    },
                                })
                            }
                        />
                    </Field>
                </>
            )}
        </div>
    );
}
export function RewardSettings({
    value,
    onChange,
}: {
    value: string;
    onChange: (value: string) => void;
}) {
    const settings = parse(value);
    const save = (next: Rewards) => onChange(JSON.stringify(next));
    return (
        <div className="space-y-5">
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
                        <Field
                            label={`${label} reputation`}
                            htmlFor={`${outcome}-reputation`}
                        >
                            <Input
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
