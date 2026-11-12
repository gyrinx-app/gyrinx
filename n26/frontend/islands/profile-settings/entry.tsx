import { mount as mountRoot } from "../../runtime/mount";
import { ProfileSettings, type ProfileSettingsProps } from "./ProfileSettings";
export function mount(element: HTMLElement, props: ProfileSettingsProps) {
    return mountRoot(element, ProfileSettings, props);
}
