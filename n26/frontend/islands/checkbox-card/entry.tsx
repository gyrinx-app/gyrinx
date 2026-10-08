import { mount as mountRoot } from "../../runtime/mount";
import {
    CheckboxCardIsland,
    type CheckboxCardIslandProps,
} from "./CheckboxCardIsland";

function take(element: Element | null): ChildNode[] {
    if (!element) return [];
    const nodes = Array.from(element.childNodes);
    // createRoot replaces the host. Detach first so these controls stay in
    // the form and keep what was already typed or ticked.
    for (const node of nodes) node.remove();
    return nodes;
}

export function mount(element: HTMLElement, props: CheckboxCardIslandProps) {
    const box = element.querySelector<HTMLInputElement>(
        "[data-checkbox-card] > label > input[type='checkbox']",
    );
    const restoreFocus = box != null && document.activeElement === box;
    return mountRoot(element, CheckboxCardIsland, {
        ...props,
        checked: box ? box.checked : props.checked,
        restoreFocus,
        metaNodes: take(element.querySelector("[data-checkbox-meta]")),
        bodyNodes: take(element.querySelector("[data-checkbox-body]")),
    });
}
