import { mount as mountRoot } from "../../runtime/mount";
import { HirePrice, type HirePriceProps } from "./HirePrice";

export function mount(element: HTMLElement, props: HirePriceProps) {
    // The server-drawn box is editable before this module loads. Start from
    // what is typed there, or a slow load would put the quote back.
    const typed = element.querySelector<HTMLInputElement>(
        `input[name="${props.field}"]`,
    )?.value;
    return mountRoot(element, HirePrice, { ...props, initial: typed });
}
