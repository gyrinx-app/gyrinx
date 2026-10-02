import { mount as mountRoot } from "../../runtime/mount";
import { RatingTooltip, type RatingTooltipProps } from "./RatingTooltip";

export function mount(element: HTMLElement, props: RatingTooltipProps) {
    return mountRoot(element, RatingTooltip, props);
}
