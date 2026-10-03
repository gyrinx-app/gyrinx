import { mount as mountRoot } from "../../runtime/mount";
import { AssetSelection, type AssetSelectionProps } from "./AssetSelection";
export function mount(element: HTMLElement, props: AssetSelectionProps) {
    return mountRoot(element, AssetSelection, props);
}
