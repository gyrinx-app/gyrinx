import { mount as mountRoot } from "../../runtime/mount";
import { AccountMenu, type AccountMenuProps } from "./AccountMenu";

export function mount(element: HTMLElement, props: AccountMenuProps) {
    return mountRoot(element, AccountMenu, props);
}
