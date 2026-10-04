import { mount as mountRoot } from "../../runtime/mount";
import { TradePoints, type TradePointsProps } from "./TradePoints";

export function mount(element: HTMLElement, props: TradePointsProps) {
    return mountRoot(element, TradePoints, props);
}
