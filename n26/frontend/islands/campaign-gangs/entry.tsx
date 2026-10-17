import { mount as mountRoot } from "../../runtime/mount";
import { CampaignGangs } from "./CampaignGangs";
import type { CampaignGangsProps } from "./table";

import { openCampaignDialog, guardDialogSubmission } from "../../ui";
export { openCampaignDialog, guardDialogSubmission } from "../../ui";

export function mount(element: HTMLElement, props: CampaignGangsProps) {
    const source = element.closest<HTMLElement>("#n26-campaign-gangs");
    function submitting(event: Event) {
        const form = event.target;
        const verb = (event as CustomEvent<{ requestConfig: { verb: string } }>)
            .detail.requestConfig.verb;
        if (
            verb.toLowerCase() !== "post" ||
            !(form instanceof HTMLFormElement) ||
            !form.closest(
                "#n26-campaign-state-dialog-host, #n26-asset-dialog-host, #n26-roll-dialog-host",
            )
        )
            return;
        guardDialogSubmission(form, () => window.location.reload());
    }
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
    document.addEventListener("htmx:beforeRequest", submitting);
    const dispose = mountRoot(element, CampaignGangs, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
    return () => {
        window.removeEventListener("popstate", restoreDialogs);
        document.removeEventListener("htmx:beforeRequest", submitting);
        dispose();
    };
}
