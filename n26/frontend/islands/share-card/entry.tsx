import { mount as mountRoot } from "../../runtime/mount";
import { ShareCard, type ShareCardProps } from "./ShareCard";

export function mount(element: HTMLElement, props: ShareCardProps) {
    return mountRoot(element, ShareCard, props);
}
