import { expect, test, vi } from "vitest";
import { registerCampaignDialogLifecycle } from "./campaignNavigation";

test("dialog lifecycle is shared until the last island unmounts", () => {
    const host = document.createElement("div");
    host.id = "n26-roll-dialog-host";
    const dialog = document.createElement("dialog");
    dialog.setAttribute("open", "");
    dialog.close = vi.fn();
    host.append(dialog);
    document.body.append(host);
    const first = registerCampaignDialogLifecycle();
    const second = registerCampaignDialogLifecycle();
    try {
        window.dispatchEvent(new PopStateEvent("popstate"));
        expect(dialog.close).toHaveBeenCalledTimes(1);
        expect(dialog.close).toHaveBeenCalledWith("n26-history");
        first();
        first();
        window.dispatchEvent(new PopStateEvent("popstate"));
        expect(dialog.close).toHaveBeenCalledTimes(2);
        second();
        window.dispatchEvent(new PopStateEvent("popstate"));
        expect(dialog.close).toHaveBeenCalledTimes(2);
    } finally {
        first();
        second();
        host.remove();
    }
});

test("inventory dialogs guard delayed posts without requiring a gang island", () => {
    const host = document.createElement("div");
    host.id = "n26-asset-dialog-host";
    const form = document.createElement("form");
    host.append(form);
    document.body.append(host);
    const release = registerCampaignDialogLifecycle();
    try {
        window.history.replaceState(null, "", "/campaign/?asset_sort=-income");
        form.dispatchEvent(
            new CustomEvent("htmx:beforeRequest", {
                bubbles: true,
                detail: { requestConfig: { verb: "post" } },
            }),
        );
        const response = new CustomEvent("htmx:beforeOnLoad", {
            cancelable: true,
        });
        form.dispatchEvent(response);
        expect(response.defaultPrevented).toBe(false);
        release();
        form.dispatchEvent(
            new CustomEvent("htmx:beforeRequest", {
                bubbles: true,
                detail: { requestConfig: { verb: "post" } },
            }),
        );
        window.history.replaceState(null, "", "/campaign/?asset_sort=name");
        const afterUnmount = new CustomEvent("htmx:beforeOnLoad", {
            cancelable: true,
        });
        form.dispatchEvent(afterUnmount);
        expect(afterUnmount.defaultPrevented).toBe(false);
    } finally {
        release();
        host.remove();
    }
});
