export type CampaignEffectsProps = {
    label: string;
    effects: string;
};

export function CampaignEffects({ label, effects }: CampaignEffectsProps) {
    if (!effects.trim()) return null;
    return (
        <details className="text-sm">
            <summary className="cursor-pointer font-medium focus-ring">
                {label}
            </summary>
            <p className="mt-2 whitespace-pre-line [overflow-wrap:anywhere]">
                {effects}
            </p>
        </details>
    );
}
