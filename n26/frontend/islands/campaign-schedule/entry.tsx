import { mount as mountRoot } from "../../runtime/mount";
import { CampaignSchedule } from "./CampaignSchedule";
import type { ScheduleProps } from "./types";
export function mount(element: HTMLElement, props: ScheduleProps) {
    return mountRoot(element, CampaignSchedule, props);
}
