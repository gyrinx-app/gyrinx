import { mount as mountRoot } from "../../runtime/mount";
import { AccountPassword, type AccountPasswordProps } from "./AccountPassword";
export function mount(element: HTMLElement, props: AccountPasswordProps) {
    return mountRoot(element, AccountPassword, props);
}
