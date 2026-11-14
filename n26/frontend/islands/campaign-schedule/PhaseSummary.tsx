import type { ReactNode } from "react";
import { HelpPopover } from "../../ui";
import type { Credits, Rewards } from "./types";

export function creditsText(amount: Credits | undefined) {
    if (!amount) return "0¢";
    const dice = amount.dice;
    const expression = dice
        ? `${dice.count}D${dice.sides}${dice.multiplier !== 1 ? ` × ${dice.multiplier}` : ""}`
        : "";
    return `${expression}${expression && amount.fixed ? " + " : ""}${amount.fixed || !expression ? amount.fixed : ""}¢`;
}

function rewardsText(rewards: Rewards) {
    const summary: string[] = [];
    for (const outcome of ["win", "draw", "loss"] as const) {
        const reward = rewards[outcome];
        if (!reward) continue;
        const amounts: string[] = [];
        if (reward.credits.fixed || reward.credits.dice)
            amounts.push(creditsText(reward.credits));
        if (reward.reputation) amounts.push(`${reward.reputation} reputation`);
        if (amounts.length)
            summary.push(
                `${{ win: "Win", draw: "Draw", loss: "Loss" }[outcome]}: ${amounts.join(", ")}`,
            );
    }
    const entry = rewards.entry_credits;
    if (entry?.fixed || entry?.dice)
        summary.push(`Phase entry: ${creditsText(entry)}`);
    return summary.join(" · ");
}

export function PhaseSummary({
    name,
    number,
    count,
    countLabel,
    description,
    effects,
    rewards,
    actions,
    showName = true,
    headingId,
    status,
}: {
    name: string;
    number?: number;
    count?: number;
    countLabel?: string;
    description?: string;
    effects?: string;
    rewards?: Rewards;
    actions?: ReactNode;
    showName?: boolean;
    headingId?: string;
    status?: ReactNode;
}) {
    const rewardSummary = rewards ? rewardsText(rewards) : "";
    return (
        <div className="min-w-0 w-full">
            <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
                    {showName && (
                        <h3
                            id={headingId}
                            aria-label={
                                number === undefined
                                    ? undefined
                                    : `Phase ${number}: ${name}`
                            }
                            className="font-medium [overflow-wrap:anywhere]"
                        >
                            {number !== undefined && (
                                <span className="text-muted">{number}. </span>
                            )}
                            {name}
                        </h3>
                    )}
                    {status}
                    {count !== undefined && (
                        <span className="text-xs text-muted">
                            {count}{" "}
                            {countLabel ?? (count === 1 ? "cycle" : "cycles")}
                        </span>
                    )}
                    {rewardSummary && (
                        <span className="text-xs text-muted">
                            {rewardSummary}
                        </span>
                    )}
                </div>
                {(effects || actions) && (
                    <div className="flex shrink-0 items-center gap-2">
                        {effects && (
                            <HelpPopover
                                label={`Effects for ${name}`}
                                triggerContent="Effects"
                            >
                                <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">
                                    {effects}
                                </p>
                            </HelpPopover>
                        )}
                        {actions}
                    </div>
                )}
            </div>
            {description && (
                <p className="mt-1 whitespace-pre-wrap text-sm text-muted [overflow-wrap:anywhere]">
                    {description}
                </p>
            )}
        </div>
    );
}
