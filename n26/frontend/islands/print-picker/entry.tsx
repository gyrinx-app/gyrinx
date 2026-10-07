import { mount as mountRoot } from "../../runtime/mount";
import { PrintPicker, type PrintPickerProps } from "./PrintPicker";

export function mount(element: HTMLElement, props: PrintPickerProps) {
    return mountRoot(element, PrintPicker, props);
}
