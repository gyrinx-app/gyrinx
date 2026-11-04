import { mount as mountRoot } from "../../runtime/mount";
import { GangTactics, type GangTacticsProps } from "./GangTactics";

export function mount(element: HTMLElement, props: GangTacticsProps) {
    return mountRoot(element, GangTactics, props);
}
