import { mount as mountRoot } from "../../runtime/mount";
import { ModelPreview, type ModelPreviewProps } from "../../ui";

export function mount(element: HTMLElement, props: ModelPreviewProps) {
    return mountRoot(element, ModelPreview, props);
}
