import { mount as mountRoot } from "../../runtime/mount";
import {
    CampaignGangPicker,
    type CampaignGangPickerProps,
} from "./CampaignGangPicker";

export function mount(element: HTMLElement, props: CampaignGangPickerProps) {
    return mountRoot(element, CampaignGangPicker, props);
}
