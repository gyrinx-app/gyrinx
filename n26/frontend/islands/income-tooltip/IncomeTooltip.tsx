import { HelpPopover } from "../../ui";

export type IncomeTooltipProps = {
    value: number;
    contributed: number;
    adjustment: number;
};

export function IncomeTooltip({
    value,
    contributed,
    adjustment,
}: IncomeTooltipProps) {
    return (
        <HelpPopover
            label={`Income breakdown: ${value}¢`}
            triggerContent={
                <span className="tabular-nums" data-counter-value>
                    {value}
                </span>
            }
        >
            <dl className="space-y-2">
                <div className="flex justify-between gap-4">
                    <dt>Contributions</dt>
                    <dd className="tabular-nums">{contributed}¢</dd>
                </div>
                <div className="flex justify-between gap-4">
                    <dt>Manual adjustment</dt>
                    <dd className="tabular-nums">{adjustment}¢</dd>
                </div>
            </dl>
        </HelpPopover>
    );
}
