import { mount as mountRoot } from "../../runtime/mount";
import { AuthoringList, type AuthoringListProps } from "./AuthoringList";

export function mount(element: HTMLElement, props: AuthoringListProps) {
    return mountRoot(element, AuthoringList, props);
}
