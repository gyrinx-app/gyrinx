import { mount as mountRoot } from "../../runtime/mount";
import { ActionMenu, type ActionMenuProps } from "../../ui";

export function mount(element: HTMLElement, props: ActionMenuProps) {
    return mountRoot(element, ActionMenu, props);
}
