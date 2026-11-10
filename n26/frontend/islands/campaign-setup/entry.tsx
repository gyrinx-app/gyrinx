import { mount as mountRoot } from "../../runtime/mount";
import { CampaignSetup, type CampaignSetupProps } from "./CampaignSetup";
export function mount(element: HTMLElement, props: CampaignSetupProps) {
    return mountRoot(element, CampaignSetup, props);
}
