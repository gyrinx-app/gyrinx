import { mount as mountRoot } from "../../runtime/mount";
import { ModelOptions, type ModelOptionsProps } from "./ModelOptions";
export function mount(element: HTMLElement, props: ModelOptionsProps) {
    return mountRoot(element, ModelOptions, props);
}
