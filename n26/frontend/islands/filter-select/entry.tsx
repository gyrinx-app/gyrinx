import { mount as mountRoot } from "../../runtime/mount";
import { FilterSelect, type FilterSelectProps } from "./FilterSelect";

export function mount(element: HTMLElement, props: FilterSelectProps) {
    return mountRoot(element, FilterSelect, props);
}
