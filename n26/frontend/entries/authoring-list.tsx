import { AuthoringList, type AuthoringListProps } from "../AuthoringList";
import { mount as mountRoot } from "../mount";

export function mount(element: HTMLElement, props: AuthoringListProps) {
    return mountRoot(element, AuthoringList, props);
}
