import { mount as mountRoot } from "../../runtime/mount";
import { Equip } from "./Equip";
import type { EquipProps } from "./types";
export function mount(element: HTMLElement, props: EquipProps) {
    return mountRoot(element, Equip, props);
}
