import { mount as mountRoot } from "../../runtime/mount";
import { ProfileSort, type ProfileSortProps } from "./ProfileSort";
export function mount(element: HTMLElement, props: ProfileSortProps) {
    return mountRoot(element, ProfileSort, props);
}
