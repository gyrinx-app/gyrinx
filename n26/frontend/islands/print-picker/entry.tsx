import { mount as mountRoot } from "../../runtime/mount";
import { PrintPicker, type PrintPickerProps } from "./PrintPicker";

export function mount(element: HTMLElement, props: PrintPickerProps) {
    // The server-drawn boxes can be ticked before this module loads, and
    // the browser restores their state on Back. Start from what they show,
    // or the island would put the ticks back and Print would save that.
    // A weapon keeps its tick even if its box is disabled. If one of those
    // boxes has focus, put it back on the replacement.
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
