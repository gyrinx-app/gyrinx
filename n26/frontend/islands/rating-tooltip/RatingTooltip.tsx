import { HelpPopover, RatingReceipt, type RatingReceiptProps } from "../../ui";

export interface RatingTooltipProps {
    name: string;
    rating: number;
    baseRating?: number;
    defaultBaseRating?: number;
    receipt?: RatingReceiptProps;
}

export function RatingTooltip({
    name,
    rating,
    baseRating,
    defaultBaseRating,
    receipt,
}: RatingTooltipProps) {
    return (
        <HelpPopover
            label={
                receipt
                    ? `${name}'s rating breakdown`
                    : `${name}'s rating includes a base rating override`
            }
            triggerContent={`${rating}¢`}
        >
            {receipt ? (
                <RatingReceipt {...receipt} />
            ) : (
                <>
                    <p>Base rating overridden to {baseRating}¢.</p>
                    <p>
                        Base rating without an override: {defaultBaseRating}¢.
                    </p>
                    <p>Equipment and advancements add to this figure.</p>
                </>
            )}
        </HelpPopover>
    );
}
