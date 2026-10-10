import { mount as mountRoot } from "../../runtime/mount";
import {
    CheckboxCardIsland,
    type CheckboxCardIslandProps,
} from "./CheckboxCardIsland";

export function mount(element: HTMLElement, props: CheckboxCardIslandProps) {
    // Read the server-drawn box before React replaces it, so a tick made
    // before the island loaded, and the focus, carry over.
    const box = element.querySelector<HTMLInputElement>(
        "[data-checkbox-card] > label > input[type='checkbox']",
    );
    return mountRoot(element, CheckboxCardIsland, {
        ...props,
        checked: box ? box.checked : props.checked,
        restoreFocus: box != null && document.activeElement === box,
    });
}
