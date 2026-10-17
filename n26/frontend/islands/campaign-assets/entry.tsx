import { mount as mountRoot } from "../../runtime/mount";
import { openCampaignDialog } from "../../ui";
import { CampaignAssets } from "./CampaignAssets";
import type { CampaignAssetsProps } from "./table";

export function mount(element: HTMLElement, props: CampaignAssetsProps) {
    const source = element.closest<HTMLElement>("#n26-campaign-assets");
    return mountRoot(element, CampaignAssets, {
        ...props,
        onOpenDialog: (href: string) => openCampaignDialog(source, href),
    });
}
