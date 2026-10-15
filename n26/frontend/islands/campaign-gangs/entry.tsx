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
    const view = window.location.pathname + window.location.search;
    function received(event: Event) {
        if (window.location.pathname + window.location.search !== view) {
            event.preventDefault();
            return;
        }
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
    function restoreDialogs() {
        for (const id of [
            "n26-campaign-state-dialog-host",
            "n26-asset-dialog-host",
            "n26-roll-dialog-host",
        ]) {
            document
                .querySelector<HTMLDialogElement>(`#${id} dialog[open]`)
                ?.close("n26-history");
        }
    }
    window.addEventListener("popstate", restoreDialogs);
    const dispose = mountRoot(element, CampaignGangs, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
    return () => {
        window.removeEventListener("popstate", restoreDialogs);
        dispose();
    };
}
