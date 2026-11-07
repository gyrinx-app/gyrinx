import { mount as mountRoot } from "../../runtime/mount";
import {
    ScenarioAuthoring,
    type ScenarioAuthoringProps,
} from "./ScenarioAuthoring";

export function mount(element: HTMLElement, props: ScenarioAuthoringProps) {
    return mountRoot(element, ScenarioAuthoring, props);
}
