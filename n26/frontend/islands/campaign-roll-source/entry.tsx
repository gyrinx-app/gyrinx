import { mount as mountRoot } from "../../runtime/mount";
import {
    CampaignRollSource,
    type CampaignRollSourceProps,
} from "./CampaignRollSource";

export function mount(element: HTMLElement, props: CampaignRollSourceProps) {
    return mountRoot(element, CampaignRollSource, props);
}
