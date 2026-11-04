import { mount as mountRoot } from "../../runtime/mount";
import { ScenarioPicks, type ScenarioPicksProps } from "./ScenarioPicks";

export function mount(element: HTMLElement, props: ScenarioPicksProps) {
    return mountRoot(element, ScenarioPicks, props);
}
