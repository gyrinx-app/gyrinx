import type { MouseEvent } from "react";
import { ButtonLink, Icon } from "../../ui";

export type AccessoriseLinkProps = {
    href: string;
    dialogId: string;
    label: string;
    name: string;
};

// Sit the link in the name line, without the button's vertical padding.
const IN_NAME = "ms-0.5 py-0!";

export function AccessoriseLink({
    href,
    dialogId,
    label,
    name,
}: AccessoriseLinkProps) {
    function open(event: MouseEvent<HTMLAnchorElement>) {
        // A modified click, or a link aimed at another window, is the
        // browser's to handle: open the drawn panel in a new tab, and so on.
        if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        const link = event.currentTarget;
        if (link.target && link.target !== "_self") return;
        event.preventDefault();
        link.dispatchEvent(
            new CustomEvent("n26-dialog-open", {
                bubbles: true,
                cancelable: true,
                composed: true,
                detail: { id: dialogId, url: href },
            }),
        );
    }

    return (
        <ButtonLink
            href={href}
            variant="text"
            size="xs"
            className={IN_NAME}
            aria-label={`${label} to ${name}`}
            onClick={open}
        >
            <span className="n26-icon-inline">
                <Icon name="plus" strokeWidth={2.5} />
            </span>
            {label}
        </ButtonLink>
    );
}
