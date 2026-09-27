import { HelpPopover } from "../../ui";

export type HelpProps = {
    label: string;
    paragraphs: string[];
    tone?: "help" | "warning";
};

export function Help({ label, paragraphs, tone }: HelpProps) {
    return (
        <HelpPopover label={label} tone={tone}>
            {paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
            ))}
        </HelpPopover>
    );
}
