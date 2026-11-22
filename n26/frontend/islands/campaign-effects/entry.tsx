import { mount as mountRoot } from "../../runtime/mount";
import { CampaignEffects, type CampaignEffectsProps } from "./CampaignEffects";

export function mount(element: HTMLElement, props: CampaignEffectsProps) {
    return mountRoot(element, CampaignEffects, props);
}
