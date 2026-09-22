import { mount as mountRoot } from "../../runtime/mount";
import { ModifierNaming, type ModifierNamingProps } from "./ModifierNaming";

export function mount(element: HTMLElement, props: ModifierNamingProps) {
    return mountRoot(element, ModifierNaming, props);
}
