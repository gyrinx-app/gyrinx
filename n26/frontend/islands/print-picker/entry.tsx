import { mount as mountRoot } from "../../runtime/mount";
import { PrintPicker, type PrintPickerProps } from "./PrintPicker";

export function mount(element: HTMLElement, props: PrintPickerProps) {
    // Preserve selections and focus from before mounting, including
    // back/forward restoration. Keep weapon selections even when their
    // model disables them.
    const shown = (name: string) =>
        Object.fromEntries(
            Array.from(
                element.querySelectorAll<HTMLInputElement>(
                    `input[name="${name}"]`,
                ),
                (box) => [box.value, box.checked],
            ),
        );
    const active = document.activeElement;
    const focus =
        active instanceof HTMLInputElement &&
        element.contains(active) &&
        (active.name === "fighters" || active.name === "weapons")
            ? { name: active.name, value: active.value }
            : null;
    return mountRoot(element, PrintPicker, {
        ...props,
        shown: { fighters: shown("fighters"), weapons: shown("weapons") },
        focus,
    });
}
