import { mount as mountRoot } from "../../runtime/mount";
import { Help, type HelpProps } from "./Help";

export function mount(element: HTMLElement, props: HelpProps) {
    return mountRoot(element, Help, props);
}
