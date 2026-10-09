import { mount as mountRoot } from "../../runtime/mount";
import { IncomeTooltip, type IncomeTooltipProps } from "./IncomeTooltip";

export function mount(element: HTMLElement, props: IncomeTooltipProps) {
    return mountRoot(element, IncomeTooltip, props);
}
