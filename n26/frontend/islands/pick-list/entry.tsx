import { mount as mountRoot } from "../../runtime/mount";
import { PickList, type PickListProps } from "./PickList";

export function mount(element: HTMLElement, props: PickListProps) {
    return mountRoot(element, PickList, props);
}
