import { mount as mountRoot } from "../../runtime/mount";
import { ScenarioDialog, type ScenarioDialogProps } from "./ScenarioDialog";
export function mount(element: HTMLElement, props: ScenarioDialogProps) {
    return mountRoot(element, ScenarioDialog, props);
}
