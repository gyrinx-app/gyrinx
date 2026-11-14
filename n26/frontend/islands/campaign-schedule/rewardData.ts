import type { Credits, Reward, Rewards } from "./types";

const object = (value: unknown): Record<string, unknown> =>
    value !== null && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : {};
const number = (value: unknown, fallback: number) =>
    typeof value === "number" ? value : fallback;

export function normalizeCredits(value: unknown): Credits {
    const amount = object(value);
    const dice = amount.dice;
    return {
        fixed: number(amount.fixed, 0),
        dice:
            dice !== null && typeof dice === "object" && !Array.isArray(dice)
                ? {
                      count: number(object(dice).count, 1),
                      sides: number(object(dice).sides, 6),
                      multiplier: number(object(dice).multiplier, 1),
                  }
                : null,
    };
}

export function normalizeRewards(value: unknown): Rewards {
    const settings = object(value);
    const reward = (value: unknown): Reward => {
        const outcome = object(value);
        return {
            credits: normalizeCredits(outcome.credits),
            reputation: number(outcome.reputation, 0),
        };
    };
    return {
        win: reward(settings.win),
        draw: reward(settings.draw),
        loss: reward(settings.loss),
        entry_credits: normalizeCredits(settings.entry_credits),
    };
}

export function parseRewards(value: string): Rewards {
    try {
        return normalizeRewards(JSON.parse(value));
    } catch {
        return normalizeRewards(null);
    }
}
