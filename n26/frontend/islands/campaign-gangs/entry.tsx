import { mount as mountRoot } from "../../runtime/mount";
import { openCampaignDialog, registerCampaignDialogLifecycle } from "../../ui";
import { CampaignGangs } from "./CampaignGangs";
import type { CampaignGangsProps } from "./table";

export { openCampaignDialog, guardDialogSubmission } from "../../ui";

export function mount(element: HTMLElement, props: CampaignGangsProps) {
    const source = element.closest<HTMLElement>("#n26-campaign-gangs");
    const releaseDialogs = registerCampaignDialogLifecycle();
    const dispose = mountRoot(element, CampaignGangs, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
    return () => {
        releaseDialogs();
        dispose();
    };
}
