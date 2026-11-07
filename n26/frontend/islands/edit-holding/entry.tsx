import { mount as mountRoot } from "../../runtime/mount";
import { EditHolding, type EditHoldingProps } from "./EditHolding";
export function mount(element: HTMLElement, props: EditHoldingProps) {
    return mountRoot(element, EditHolding, props);
}
