import { mount as mountRoot } from "../../runtime/mount";
import { Announcement, type AnnouncementProps } from "./Announcement";

export function mount(element: HTMLElement, props: AnnouncementProps) {
    return mountRoot(element, Announcement, props);
}
