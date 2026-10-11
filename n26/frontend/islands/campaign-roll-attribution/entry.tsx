import { mount as mountRoot } from "../../runtime/mount";
import {
    CampaignRollAttribution,
    type CampaignRollAttributionProps,
} from "./CampaignRollAttribution";

export function mount(
    element: HTMLElement,
    props: CampaignRollAttributionProps,
) {
    return mountRoot(element, CampaignRollAttribution, props);
}
