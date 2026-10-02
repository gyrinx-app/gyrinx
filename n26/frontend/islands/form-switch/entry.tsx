import { mount as mountRoot } from "../../runtime/mount";
import { FormSwitch, type FormSwitchProps } from "./FormSwitch";

export function mount(element: HTMLElement, props: FormSwitchProps) {
    return mountRoot(element, FormSwitch, props);
}
