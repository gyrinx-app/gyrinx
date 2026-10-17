import { mount as mountRoot } from "../../runtime/mount";
import { openCampaignDialog, registerCampaignDialogLifecycle } from "../../ui";
import { CampaignAssets } from "./CampaignAssets";
import type { CampaignAssetsProps } from "./table";

export function mount(element: HTMLElement, props: CampaignAssetsProps) {
    const source = element.closest<HTMLElement>("#n26-campaign-assets");
    const releaseDialogs = registerCampaignDialogLifecycle();
    const dispose = mountRoot(element, CampaignAssets, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
    return () => {
        releaseDialogs();
        dispose();
    };
}
