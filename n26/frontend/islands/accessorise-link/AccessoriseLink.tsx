import type { MouseEvent } from "react";
import { ButtonLink, Icon } from "../../ui";

export type AccessoriseLinkProps = {
    href: string;
    dialogId: string;
    label: string;
    name: string;
};

// Sit the control in the name line. The ghost recipe is a blocky button;
// these classes pull it back into the sentence beside the weapon.
const IN_NAME = "ms-0.5 -mt-0.5 align-middle text-ink-500 dark:text-ink-400";

export function AccessoriseLink({
    href,
    dialogId,
    label,
    name,
}: AccessoriseLinkProps) {
    function open(event: MouseEvent<HTMLAnchorElement>) {
        event.preventDefault();
        event.currentTarget.dispatchEvent(
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
            variant="ghost"
            size="xs"
            className={IN_NAME}
            aria-label={`${label} to ${name}`}
            onClick={open}
        >
            <span className="inline-flex items-center gap-1 whitespace-nowrap">
                <Icon name="plus" className="size-3.5" strokeWidth={2.5} />
                {label}
            </span>
        </ButtonLink>
    );
}
