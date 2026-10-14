import { useEffect, useState } from "react";
import { mount as mountRoot } from "../../runtime/mount";
import { ButtonLink, type ButtonLinkVariant } from "../../ui";

type Props = {
    href: string;
    label: string;
    variant: ButtonLinkVariant;
    className: string;
};
export function CampaignViewLink(props: Props) {
    const [search, setSearch] = useState(window.location.search);
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
    return (
        <ButtonLink
            href={url.pathname + url.search + url.hash}
            size="sm"
            variant={props.variant}
            className={props.className}
        >
            {props.label}
        </ButtonLink>
    );
}
export function mount(element: HTMLElement, props: Props) {
    return mountRoot(element, CampaignViewLink, props);
}
