import { mount as mountRoot } from "../../runtime/mount";
import {
    NotificationInbox,
    type NotificationInboxProps,
} from "./NotificationInbox";
export function mount(element: HTMLElement, props: NotificationInboxProps) {
    return mountRoot(element, NotificationInbox, props);
}
