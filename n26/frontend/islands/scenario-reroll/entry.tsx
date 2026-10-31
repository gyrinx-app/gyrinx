import { mount as mountRoot } from "../../runtime/mount";
import { ScenarioReroll, type ScenarioRerollProps } from "./ScenarioReroll";
export function mount(element: HTMLElement, props: ScenarioRerollProps) {
    return mountRoot(element, ScenarioReroll, props);
}
