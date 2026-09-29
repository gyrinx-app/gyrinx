import { mount as mountRoot } from "../../runtime/mount";
import { AdvancementRoll, type AdvancementRollProps } from "./AdvancementRoll";

export function mount(element: HTMLElement, props: AdvancementRollProps) {
    return mountRoot(element, AdvancementRoll, props);
}
