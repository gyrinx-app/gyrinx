import { mount as mountRoot } from "../../runtime/mount";
import {
    BaseRatingDialog,
    type BaseRatingDialogProps,
} from "./BaseRatingDialog";

export function mount(element: HTMLElement, props: BaseRatingDialogProps) {
    return mountRoot(element, BaseRatingDialog, props);
}
