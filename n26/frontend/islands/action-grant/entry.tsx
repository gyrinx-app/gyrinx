import { mount as mountRoot } from "../../runtime/mount";
import { ActionGrant, type ActionGrantProps } from "./ActionGrant";

export function mount(element: HTMLElement, props: ActionGrantProps) {
    return mountRoot(element, ActionGrant, props);
}
