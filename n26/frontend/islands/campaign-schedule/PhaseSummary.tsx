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
    const hasHeader = Boolean(
        showName ||
        count !== undefined ||
        rewardSummary ||
        effects ||
        actions ||
        status,
    );
    if (!hasHeader && !description) return null;
    return (
        <div className="min-w-0 w-full">
            {hasHeader && (
                <div className="flex items-start justify-between gap-3">
                    <div className="flex min-h-7 min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
                        {showName && (
                            <h3
                                id={headingId}
                                aria-label={
                                    number === undefined
                                        ? undefined
                                        : `Phase ${number}: ${name}`
                                }
                                className="text-base leading-7 font-semibold [overflow-wrap:anywhere]"
                            >
                                {number !== undefined && (
                                    <span className="tabular-nums text-muted">
                                        {String(number).padStart(2, "0")}{" "}
                                    </span>
                                )}
                                {name}
                            </h3>
                        )}
                        {status}
                        {count !== undefined && (
                            <span className="text-xs text-muted">
                                {count}{" "}
                                {countLabel ??
                                    (count === 1 ? "cycle" : "cycles")}
                            </span>
                        )}
                        {rewardSummary && (
                            <span className="text-xs text-muted">
                                {rewardSummary}
                            </span>
                        )}
                    </div>
                    {(effects || actions) && (
                        <div className="flex min-h-7 shrink-0 items-center gap-2 text-xs text-muted">
                            {effects && (
                                <HelpPopover
                                    label={`Effects for ${name}`}
                                    triggerContent="Effects"
                                    clampHeight
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
            )}
            {description && (
                <p
                    className={`${hasHeader ? "mt-1 " : ""}whitespace-pre-wrap text-sm text-muted [overflow-wrap:anywhere]`}
                >
                    {description}
                </p>
            )}
        </div>
    );
}
