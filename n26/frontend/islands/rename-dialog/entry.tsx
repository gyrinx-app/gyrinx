import { mount as mountRoot } from "../../runtime/mount";
import { RenameDialog, type RenameDialogProps } from "./RenameDialog";

export function mount(element: HTMLElement, props: RenameDialogProps) {
    return mountRoot(element, RenameDialog, props);
}
