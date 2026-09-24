import { mount as mountRoot } from "../../runtime/mount";
import {
    ModifierKindPicker,
    type ModifierKindPickerProps,
} from "./ModifierKindPicker";

export function mount(element: HTMLElement, props: ModifierKindPickerProps) {
    return mountRoot(element, ModifierKindPicker, props);
}
