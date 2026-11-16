import { mount as mountRoot } from "../../runtime/mount";
import { ReorderDemo } from "./ReorderDemo";
export function mount(element: HTMLElement, props: Record<string, never>) {
    return mountRoot(element, ReorderDemo, props);
}
