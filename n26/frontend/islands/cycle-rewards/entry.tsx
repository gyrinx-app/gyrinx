import { mount as mountRoot } from "../../runtime/mount";
import { CycleRewards, type CycleRewardsProps } from "./CycleRewards";

export function mount(element: HTMLElement, props: CycleRewardsProps) {
    return mountRoot(element, CycleRewards, props);
}
