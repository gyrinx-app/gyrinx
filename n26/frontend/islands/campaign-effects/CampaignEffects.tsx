import { HelpPopover } from "../../ui";

export type CampaignEffectsProps = {
    label: string;
    effects: string;
};

export function CampaignEffects({ label, effects }: CampaignEffectsProps) {
    if (!effects.trim()) return null;
    return (
        <div className="text-sm">
            <HelpPopover
                label={label}
                triggerContent={label}
                placement="top"
                clampHeight
            >
                <p className="whitespace-pre-line [overflow-wrap:anywhere]">
                    {effects}
                </p>
            </HelpPopover>
        </div>
    );
}
