import { mount as mountRoot } from "../../runtime/mount";
import {
    CounterAdjustment,
    type CounterAdjustmentProps,
} from "./CounterAdjustment";

export function mount(element: HTMLElement, props: CounterAdjustmentProps) {
    return mountRoot(element, CounterAdjustment, props);
}
