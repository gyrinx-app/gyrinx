import { mount as mountRoot } from "../../runtime/mount";
import {
    CheckboxCardIsland,
    type CheckboxCardIslandProps,
} from "./CheckboxCardIsland";

export function mount(element: HTMLElement, props: CheckboxCardIslandProps) {
    // Read the server-drawn boxes before React replaces them, so ticks made
    // before the island loaded, and the card box's focus, carry over.
    const box = element.querySelector<HTMLInputElement>(
        "[data-checkbox-card] > label > input[type='checkbox']",
    );
    const drawn = Array.from(
        element.querySelectorAll<HTMLInputElement>(
            "[data-checkbox-body] input[type='checkbox']",
        ),
    );
    const items = props.items.map((item) => {
        const fallback = drawn.find(
            (input) => input.name === item.name && input.value === item.value,
        );
        return fallback ? { ...item, checked: fallback.checked } : item;
    });
    const focused = drawn.find((input) => input === document.activeElement);
    return mountRoot(element, CheckboxCardIsland, {
        ...props,
        items,
        checked: box ? box.checked : props.checked,
        restoreFocus: box != null && document.activeElement === box,
        focusItem: focused
            ? { name: focused.name, value: focused.value }
            : null,
    });
}
