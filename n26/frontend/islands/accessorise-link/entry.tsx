import { mount as mountRoot } from "../../runtime/mount";
import { AccessoriseLink, type AccessoriseLinkProps } from "./AccessoriseLink";

export function mount(element: HTMLElement, props: AccessoriseLinkProps) {
    return mountRoot(element, AccessoriseLink, props);
}
