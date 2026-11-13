import { mount as mountRoot } from "../../runtime/mount";
import { ChoiceWorkflow, type ChoiceWorkflowProps } from "./ChoiceWorkflow";

export function mount(element: HTMLElement, props: ChoiceWorkflowProps) {
    return mountRoot(element, ChoiceWorkflow, props);
}
