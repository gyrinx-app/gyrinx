import { mount as mountRoot } from "../../runtime/mount";
import { HirePrice, type HirePriceProps } from "./HirePrice";

export function mount(element: HTMLElement, props: HirePriceProps) {
    // Preserve edits made before module loading so mounting cannot restore
    // an outdated quote.
    const typed = element.querySelector<HTMLInputElement>(
        `input[name="${props.field}"]`,
    )?.value;
    return mountRoot(element, HirePrice, { ...props, initial: typed });
}
