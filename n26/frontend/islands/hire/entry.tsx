import { mount as mountRoot } from "../../runtime/mount";
import { Hire } from "./Hire";
import type { HireProps } from "./types";

export function mount(element: HTMLElement, props: HireProps) {
    return mountRoot(element, Hire, props);
}
