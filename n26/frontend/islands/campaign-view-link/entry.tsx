import { useEffect, useRef, useState, type MouseEvent } from "react";
import { mount as mountRoot } from "../../runtime/mount";
import { ButtonLink, type ButtonLinkVariant } from "../../ui";

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
    const url = new URL(props.href, window.location.href);
    const query = new URLSearchParams(search);
    for (const key of ["sort", "group"]) {
        if (query.has(key)) url.searchParams.set(key, query.get(key)!);
        else url.searchParams.delete(key);
    }
    const href = url.pathname + url.search + url.hash;
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
            await props.onOpenDialog?.(href);
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
    return mountRoot(element, CampaignViewLink, {
        ...props,
        onOpenDialog: async (href: string) => {
            const htmx = (
                window as Window & {
                    htmx?: {
                        ajax: (
                            method: string,
                            href: string,
                            options: { source: HTMLElement; swap: string },
                        ) => Promise<unknown>;
                    };
                }
            ).htmx;
            if (!source || !htmx) throw new Error("Dialog unavailable");
            let answered = false;
            function received(event: Event) {
                const xhr = (event as CustomEvent<{ xhr: XMLHttpRequest }>)
                    .detail.xhr;
                answered =
                    xhr.status === 200 &&
                    xhr.getResponseHeader("HX-Replace-Url") !== null;
            }
            source.addEventListener("htmx:beforeOnLoad", received);
            try {
                await htmx.ajax("GET", href, { source, swap: "none" });
                if (!answered) throw new Error("Dialog unavailable");
            } finally {
                source.removeEventListener("htmx:beforeOnLoad", received);
            }
        },
    });
}
