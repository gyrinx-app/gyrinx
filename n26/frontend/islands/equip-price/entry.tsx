import { mount as mountRoot } from "../../runtime/mount";
import { EquipPrice, type EquipPriceProps } from "./EquipPrice";

export function mount(element: HTMLElement, props: EquipPriceProps) {
    // The server-drawn box is editable before this module loads. Start from
    // what is typed there, or a slow load would put the quote back.
    const typed = element.querySelector<HTMLInputElement>(
        `input[name="${props.field}"]`,
    )?.value;
    return mountRoot(element, EquipPrice, { ...props, initial: typed });
}
