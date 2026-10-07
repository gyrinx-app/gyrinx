import { mount as mountRoot } from "../../runtime/mount";
import { EquipPrice, type EquipPriceProps } from "./EquipPrice";

export function mount(element: HTMLElement, props: EquipPriceProps) {
    // The server-drawn box is editable before this module loads. Start from
    // what is typed there, or a slow load would put the quote back. If that
    // box still has focus, put it back on the replacement so the next
    // keystroke is not lost.
    const box = element.querySelector<HTMLInputElement>(
        `input[name="${props.field}"]`,
    );
    const restoreFocus = box != null && document.activeElement === box;
    let selectionStart: number | null = null;
    let selectionEnd: number | null = null;
    if (restoreFocus && box) {
        try {
            selectionStart = box.selectionStart;
            selectionEnd = box.selectionEnd;
        } catch {
            selectionStart = null;
            selectionEnd = null;
        }
    }
    return mountRoot(element, EquipPrice, {
        ...props,
        initial: box?.value,
        restoreFocus,
        selectionStart,
        selectionEnd,
    });
}
