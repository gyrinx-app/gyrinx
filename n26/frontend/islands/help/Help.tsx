import { HelpPopover } from "../../ui";

export type HelpProps = {
    label: string;
    paragraphs: string[];
};

export function Help({ label, paragraphs }: HelpProps) {
    return (
        <HelpPopover label={label}>
            {paragraphs.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
            ))}
        </HelpPopover>
    );
}
