import { useEffect, useRef, useState } from "react";

const VIEW_KEYS = ["sort", "group", "asset_sort", "asset_group"];

export function campaignViewHref(
    href: string,
    search = window.location.search,
) {
    const url = new URL(href, window.location.href);
    const query = new URLSearchParams(search);
    for (const key of VIEW_KEYS) {
        if (query.has(key)) url.searchParams.set(key, query.get(key)!);
        else url.searchParams.delete(key);
    }
    return url.pathname + url.search + url.hash;
}

export function useCampaignDialogRequests() {
    const requests = useRef(new Set<unknown>());
    const [pending, setPending] = useState(false);
    useEffect(() => {
        function changed(event: Event) {
            const { request, pending } = (
                event as CustomEvent<{ request: unknown; pending: boolean }>
            ).detail;
            if (pending) requests.current.add(request);
            else requests.current.delete(request);
            setPending(requests.current.size > 0);
        }
        window.addEventListener("n26:campaign-dialog-request", changed);
        return () =>
            window.removeEventListener("n26:campaign-dialog-request", changed);
    }, []);
    return { pending, requests };
}

export async function openCampaignDialog(
    source: HTMLElement | null,
    href: string,
) {
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
        await htmx.ajax("GET", href, { source, swap: "none" });
        if (!answered) throw new Error("Dialog unavailable");
    } finally {
        source.removeEventListener("htmx:beforeOnLoad", received);
    }
}

export function guardDialogSubmission(
    form: HTMLFormElement,
    refresh: () => void,
) {
    const view = window.location.pathname + window.location.search;
    form.addEventListener(
        "htmx:beforeOnLoad",
        (event) => {
            if (window.location.pathname + window.location.search !== view) {
                event.preventDefault();
                // A completed write needs fresh facts at the current view.
                refresh();
            }
        },
        { once: true },
    );
}

export async function runCampaignDialog(
    open: () => Promise<unknown> | undefined,
) {
    const request = {};
    const notify = (pending: boolean) =>
        window.dispatchEvent(
            new CustomEvent("n26:campaign-dialog-request", {
                detail: { request, pending },
            }),
        );
    notify(true);
    try {
        await open();
    } finally {
        notify(false);
    }
}
