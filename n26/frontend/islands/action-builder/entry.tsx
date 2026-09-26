import { mount as mountRoot } from "../../runtime/mount";
import { ActionBuilder, type ActionBuilderProps } from "./ActionBuilder";

export function mount(element: HTMLElement, props: ActionBuilderProps) {
    return mountRoot(element, ActionBuilder, props);
}
