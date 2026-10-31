import { mount as mountRoot } from "../../runtime/mount";
import { RichTextMode, type RichTextModeProps } from "./RichTextMode";

export function mount(element: HTMLElement, props: RichTextModeProps) {
    return mountRoot(element, RichTextMode, props);
}
