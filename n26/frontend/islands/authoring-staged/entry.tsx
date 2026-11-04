import { mount as mountRoot } from "../../runtime/mount";
import { StagedContent, type StagedContentProps } from "./StagedContent";

export function mount(element: HTMLElement, props: StagedContentProps) {
    return mountRoot(element, StagedContent, props);
}
