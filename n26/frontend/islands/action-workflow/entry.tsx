import { mount as mountRoot } from "../../runtime/mount";
import { ActionWorkflow, type ActionWorkflowProps } from "./ActionWorkflow";

export function mount(element: HTMLElement, props: ActionWorkflowProps) {
    return mountRoot(element, ActionWorkflow, props);
}
