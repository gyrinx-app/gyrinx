import { mount as mountRoot } from "../../runtime/mount";
import { QuickSwitcher, type QuickSwitcherProps } from "../../ui";

export function mount(element: HTMLElement, props: QuickSwitcherProps) {
    return mountRoot(element, QuickSwitcher, props);
}
