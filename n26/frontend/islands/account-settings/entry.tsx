import { mount as mountRoot } from "../../runtime/mount";
import { AccountSettings, type AccountSettingsProps } from "./AccountSettings";
export function mount(element: HTMLElement, props: AccountSettingsProps) {
    return mountRoot(element, AccountSettings, props);
}
