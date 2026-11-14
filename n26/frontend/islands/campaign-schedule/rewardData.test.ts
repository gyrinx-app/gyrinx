import { expect, test } from "vitest";
import { normalizeRewards, parseRewards } from "./rewardData";

const blankCredits = { fixed: 0, dice: null };
const blankReward = { credits: blankCredits, reputation: 0 };
const blank = {
    win: blankReward,
    draw: blankReward,
    loss: blankReward,
    entry_credits: blankCredits,
};

test.each([
    undefined,
    {},
    { win: {} },
    { draw: { credits: {} } },
    { loss: {} },
    { entry_credits: {} },
])("omitted reward fields use backend defaults (%j)", (value) =>
    expect(normalizeRewards(value)).toEqual(blank),
);

test.each(["win", "draw", "loss", "entry_credits"] as const)(
    "%s retains sparse dice using backend component defaults",
    (key) => {
        for (const [dice, expected] of [
            [{}, { count: 1, sides: 6, multiplier: 1 }],
            [{ count: 2 }, { count: 2, sides: 6, multiplier: 1 }],
            [{ sides: 3 }, { count: 1, sides: 3, multiplier: 1 }],
            [{ multiplier: 10 }, { count: 1, sides: 6, multiplier: 10 }],
            [
                { count: 2, sides: 3, multiplier: 5 },
                { count: 2, sides: 3, multiplier: 5 },
            ],
        ]) {
            const credits = { dice };
            const result = normalizeRewards({
                [key]: key === "entry_credits" ? credits : { credits },
            });
            expect(
                key === "entry_credits" ? result[key] : result[key].credits,
            ).toEqual({ fixed: 0, dice: expected });
        }
    },
);

test("complete DTOs retain their amounts and normalization does not mutate sparse input", () => {
    const full = {
        win: {
            credits: { fixed: 10, dice: { count: 2, sides: 3, multiplier: 5 } },
            reputation: -1,
        },
        draw: blankReward,
        loss: blankReward,
        entry_credits: { fixed: 20, dice: null },
    };
    expect(normalizeRewards(full)).toEqual(full);
    expect(parseRewards(JSON.stringify(full))).toEqual(full);
    const sparse = { win: { credits: { dice: {} } } };
    normalizeRewards(sparse);
    expect(sparse).toEqual({ win: { credits: { dice: {} } } });
});

test("the string adapter handles empty or malformed stored settings", () => {
    expect(parseRewards("")).toEqual(blank);
    expect(parseRewards("null")).toEqual(blank);
    expect(parseRewards("{")).toEqual(blank);
});
