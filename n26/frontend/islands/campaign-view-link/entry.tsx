import { useEffect, useRef, useState, type MouseEvent } from "react";
import { mount as mountRoot } from "../../runtime/mount";
import {
    ButtonLink,
    campaignViewHref,
    openCampaignDialog,
    registerCampaignDialogLifecycle,
    runCampaignDialog,
    type ButtonLinkVariant,
} from "../../ui";

type Props = {
    href: string;
    label: string;
    variant: ButtonLinkVariant;
    className: string;
    dialog?: boolean;
};
export function CampaignViewLink(
    props: Props & {
        onOpenDialog?: (href: string) => Promise<unknown>;
    },
) {
    const [search, setSearch] = useState(window.location.search);
    const [error, setError] = useState(false);
    const opening = useRef(false);
    useEffect(() => {
        const update = () => setSearch(window.location.search);
        window.addEventListener("popstate", update);
        window.addEventListener("n26:location-changed", update);
        return () => {
            window.removeEventListener("popstate", update);
            window.removeEventListener("n26:location-changed", update);
        };
    }, []);
    const href = campaignViewHref(props.href, search);
    async function open(event: MouseEvent<HTMLAnchorElement>) {
        if (
            !props.dialog ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        )
            return;
        event.preventDefault();
        if (opening.current) return;
        opening.current = true;
        setError(false);
        try {
            await runCampaignDialog(() => props.onOpenDialog?.(href));
        } catch {
            setError(true);
        } finally {
            opening.current = false;
        }
    }
    return (
        <>
            <ButtonLink
                href={href}
                size="sm"
                variant={props.variant}
                className={props.className}
                onClick={open}
            >
                {props.label}
            </ButtonLink>
            {error && (
                <span role="alert">
                    The form could not load. Reload the page and try again.
                </span>
            )}
        </>
    );
}
export function mount(element: HTMLElement, props: Props) {
    const source = element.closest<HTMLElement>("#n26-campaign-assets");
    const releaseDialogs = registerCampaignDialogLifecycle();
    const dispose = mountRoot(element, CampaignViewLink, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
    return () => {
        releaseDialogs();
        dispose();
    };
}
