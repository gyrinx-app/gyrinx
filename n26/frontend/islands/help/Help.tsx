import { HelpPopover } from "../../ui";

export type HelpProps = {
    label: string;
    triggerId?: string;
    paragraphs: string[];
    tone?: "help" | "warning";
    cta?: { label: string; href: string };
};

export function Help({ label, paragraphs, tone, cta, triggerId }: HelpProps) {
    return (
        <HelpPopover label={label} tone={tone} cta={cta} triggerId={triggerId}>
            {paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
            ))}
        </HelpPopover>
    );
}
