import { mount as mountRoot } from "../../runtime/mount";
import {
    FilterMenuIsland,
    type FilterMenuIslandProps,
} from "./FilterMenuIsland";

export function mount(element: HTMLElement, props: FilterMenuIslandProps) {
    return mountRoot(element, FilterMenuIsland, props);
}
