import { HelpPopover } from "../../ui";

export type HelpProps = {
    label: string;
    paragraphs: string[];
    tone?: "help" | "warning";
    cta?: { label: string; href: string };
};

export function Help({ label, paragraphs, tone, cta }: HelpProps) {
    return (
        <HelpPopover label={label} tone={tone} cta={cta}>
            {paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
            ))}
        </HelpPopover>
    );
}
