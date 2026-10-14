import { mount as mountRoot } from "../../runtime/mount";
import { CampaignGangs } from "./CampaignGangs";
import type { CampaignGangsProps } from "./table";

type Htmx = {
    ajax: (
        method: string,
        href: string,
        options: { source: HTMLElement; swap: string },
    ) => Promise<unknown>;
};
export async function openCampaignDialog(
    source: HTMLElement | null,
    href: string,
) {
    const htmx = (window as Window & { htmx?: Htmx }).htmx;
    if (!source || !htmx) throw new Error("Dialog unavailable");
    let answered = false;
    function received(event: Event) {
        const xhr = (event as CustomEvent<{ xhr: XMLHttpRequest }>).detail.xhr;
        answered =
            xhr.status === 200 &&
            xhr.getResponseHeader("HX-Replace-Url") !== null;
    }
    source.addEventListener("htmx:beforeOnLoad", received);
    try {
        // Only Django's outer hosts are swapped; React's children are never targets.
        await htmx.ajax("GET", href, { source, swap: "none" });
        if (!answered) throw new Error("Dialog unavailable");
    } finally {
        source.removeEventListener("htmx:beforeOnLoad", received);
    }
}
export function mount(element: HTMLElement, props: CampaignGangsProps) {
    const source = element.closest<HTMLElement>("#n26-campaign-gangs");
    return mountRoot(element, CampaignGangs, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
}
