import { mount as mountRoot } from "../../runtime/mount";
import { ModifierList, type ModifierListProps } from "./ModifierList";

export function mount(element: HTMLElement, props: ModifierListProps) {
    return mountRoot(element, ModifierList, props);
}
