import { mount as mountRoot } from "../../runtime/mount";
import { FileInput, type FileInputProps } from "./FileInput";

export function mount(element: HTMLElement, props: FileInputProps) {
    return mountRoot(element, FileInput, props);
}
