import { mount as mountRoot } from "../../runtime/mount";
import { PostBattlePreview, type PreviewDisplay } from "./PostBattlePreview";
export function mount(element: HTMLElement, props: PreviewDisplay) {
    return mountRoot(element, PostBattlePreview, props);
}
