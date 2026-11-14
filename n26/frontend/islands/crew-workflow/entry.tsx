import { mount as mountRoot } from "../../runtime/mount";
import { CrewWorkflow, type CrewWorkflowProps } from "./CrewWorkflow";

export function mount(element: HTMLElement, props: CrewWorkflowProps) {
    return mountRoot(element, CrewWorkflow, props);
}
