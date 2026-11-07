import { mount as mountRoot } from "../../runtime/mount";
import { ManageCredits, type ManageCreditsProps } from "./ManageCredits";
export function mount(element: HTMLElement, props: ManageCreditsProps) {
    return mountRoot(element, ManageCredits, props);
}
