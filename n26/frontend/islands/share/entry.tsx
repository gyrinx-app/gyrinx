import { mount as mountRoot } from "../../runtime/mount";
import { Share, type ShareProps } from "./Share";

export function mount(element: HTMLElement, props: ShareProps) {
    return mountRoot(element, Share, props);
}
