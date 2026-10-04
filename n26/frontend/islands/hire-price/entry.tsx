import { mount as mountRoot } from "../../runtime/mount";
import { HirePrice, type HirePriceProps } from "./HirePrice";

export function mount(element: HTMLElement, props: HirePriceProps) {
    return mountRoot(element, HirePrice, props);
}
