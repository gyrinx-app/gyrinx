import { mount as mountRoot } from "../../runtime/mount";
import { ScenarioLink, type ScenarioLinkProps } from "./ScenarioLink";

export function mount(element: HTMLElement, props: ScenarioLinkProps) {
    return mountRoot(element, ScenarioLink, props);
}
