import { mount as mountRoot } from "../../runtime/mount";
import { CrewPicker, type CrewPickerProps } from "./CrewPicker";

export function mount(element: HTMLElement, props: CrewPickerProps) {
    return mountRoot(element, CrewPicker, props);
}
