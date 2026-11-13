import { mount as mountRoot } from "../../runtime/mount";
import { ArbitratorToolkit, type ToolkitProps } from "./ArbitratorToolkit";
export function mount(element: HTMLElement, props: ToolkitProps) {
    return mountRoot(element, ArbitratorToolkit, props);
}
