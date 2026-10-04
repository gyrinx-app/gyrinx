import { mount as mountRoot } from "../../runtime/mount";
import {
    AccountLoginName,
    type AccountLoginNameProps,
} from "./AccountLoginName";
export function mount(element: HTMLElement, props: AccountLoginNameProps) {
    return mountRoot(element, AccountLoginName, props);
}
