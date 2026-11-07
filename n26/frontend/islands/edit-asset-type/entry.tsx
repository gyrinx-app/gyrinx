import { mount as mountRoot } from "../../runtime/mount";
import { EditAssetType, type EditAssetTypeProps } from "./EditAssetType";
export function mount(element: HTMLElement, props: EditAssetTypeProps) {
    return mountRoot(element, EditAssetType, props);
}
