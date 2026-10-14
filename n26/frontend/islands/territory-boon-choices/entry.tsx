import { mount as mountRoot } from "../../runtime/mount";
import {
    TerritoryBoonChoices,
    type TerritoryBoonChoicesProps,
} from "./TerritoryBoonChoices";

export async function saveTerritoryBoons(
    props: TerritoryBoonChoicesProps,
    values: Record<string, string>,
    signal?: AbortSignal,
) {
    const body = new URLSearchParams({ snapshot: props.snapshot });
    for (const [key, value] of Object.entries(values))
        body.set(`choice_${key}`, value);
    let response: Response;
    try {
        response = await fetch(props.saveUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": props.csrfToken,
                Accept: "application/json",
            },
            body,
            signal,
        });
    } catch {
        throw new Error("Could not save boons. Try again.");
    }
    if (
        response.redirected ||
        !response.headers.get("Content-Type")?.includes("application/json")
    )
        throw new Error("Could not save boons. Reload the page and try again.");
    const result = (await response.json()) as {
        error?: string;
        redirectUrl?: string;
    };
    if (!response.ok || !result.redirectUrl)
        throw new Error(result.error || "Could not save boons. Try again.");
    const target = new URL(result.redirectUrl, window.location.href);
    if (target.origin !== window.location.origin)
        throw new Error("Could not save boons. Reload the page and try again.");
    if (signal?.aborted) return;
    navigateToSavedTerritory(target);
}

export function navigateToSavedTerritory(target: URL) {
    if (
        target.pathname === window.location.pathname &&
        target.search === window.location.search
    ) {
        window.history.replaceState(null, "", target.href);
        window.location.reload();
    } else {
        window.location.assign(target.href);
    }
}

export function mount(element: HTMLElement, props: TerritoryBoonChoicesProps) {
    const controller = new AbortController();
    const dispose = mountRoot(element, TerritoryBoonChoices, {
        ...props,
        onSave: (values: Record<string, string>) =>
            saveTerritoryBoons(props, values, controller.signal),
    });
    return () => {
        controller.abort();
        dispose();
    };
}
