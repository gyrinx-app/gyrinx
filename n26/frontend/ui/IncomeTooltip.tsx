import { HelpPopover } from "./HelpPopover";

export type IncomePart = {
    label: string;
    amount: number;
    detail: string;
    replaced: boolean;
};

export type IncomeSource = {
    name: string;
    value: number;
    parts: IncomePart[];
};

export type IncomeTooltipProps = {
    value: number;
    contributed: number;
    adjustment: number;
    sources?: IncomeSource[];
    currency?: boolean;
    showAdjustment?: boolean;
};

function signedAmount(amount: number) {
    return `${amount > 0 ? "+" : ""}${amount}¢`;
}

export function IncomeTooltip({
    value,
    contributed,
    adjustment,
    sources,
    currency = false,
    showAdjustment = true,
}: IncomeTooltipProps) {
    return (
        <HelpPopover
            label={`Income breakdown: ${value}¢`}
            triggerContent={
                <span className="tabular-nums" data-counter-value>
                    {value}
                    {currency && "¢"}
                </span>
            }
        >
            <div className="space-y-3 text-left text-sm">
                <div
                    role="region"
                    aria-label="Income breakdown details"
                    tabIndex={0}
                    className="max-h-[min(24rem,calc(50dvh-8rem))] space-y-3 overflow-y-auto overscroll-contain rounded-sm pr-1 focus-ring"
                >
                    {sources?.length ? (
                        sources.map((source, sourceIndex) => (
                            <section key={sourceIndex} className="space-y-1">
                                <div className="flex items-baseline justify-between gap-3 font-medium">
                                    <h3 className="min-w-0 break-words [overflow-wrap:anywhere]">
                                        {source.name}
                                    </h3>
                                    <span className="shrink-0 whitespace-nowrap tabular-nums">
                                        {source.value}¢
                                    </span>
                                </div>
                                <dl className="space-y-1 text-muted">
                                    {source.parts.map((part, partIndex) => (
                                        <div
                                            key={partIndex}
                                            className="flex items-baseline justify-between gap-3"
                                        >
                                            <dt className="min-w-0 break-words [overflow-wrap:anywhere]">
                                                <span>{part.label}</span>
                                                {part.detail && (
                                                    <span className="block text-xs">
                                                        {part.detail}
                                                    </span>
                                                )}
                                                {part.replaced && (
                                                    <span className="block text-xs">
                                                        Replaced by override;
                                                        excluded from total.
                                                    </span>
                                                )}
                                            </dt>
                                            <dd className="shrink-0 whitespace-nowrap tabular-nums">
                                                {part.replaced ? (
                                                    <s>
                                                        {signedAmount(
                                                            part.amount,
                                                        )}
                                                    </s>
                                                ) : (
                                                    signedAmount(part.amount)
                                                )}
                                            </dd>
                                        </div>
                                    ))}
                                </dl>
                            </section>
                        ))
                    ) : (
                        <dl>
                            <div className="flex items-baseline justify-between gap-3">
                                <dt className="min-w-0 break-words">
                                    Contributions
                                </dt>
                                <dd className="shrink-0 whitespace-nowrap tabular-nums">
                                    {contributed}¢
                                </dd>
                            </div>
                        </dl>
                    )}
                </div>
                <dl className="space-y-2">
                    {showAdjustment && (
                        <div className="flex items-baseline justify-between gap-3">
                            <dt className="min-w-0 break-words">
                                Manual adjustment
                            </dt>
                            <dd className="shrink-0 whitespace-nowrap tabular-nums">
                                {adjustment}¢
                            </dd>
                        </div>
                    )}
                    <div className="flex items-baseline justify-between gap-3 border-t border-dashed border-box-border pt-2 font-semibold">
                        <dt>Total income</dt>
                        <dd className="shrink-0 whitespace-nowrap tabular-nums">
                            {value}¢
                        </dd>
                    </div>
                </dl>
            </div>
        </HelpPopover>
    );
}
