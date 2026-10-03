import { mount as mountRoot } from "../../runtime/mount";
import { PostBattleToolbar, type ToolbarProps } from "./PostBattleToolbar";
export function mount(element: HTMLElement, props: ToolbarProps) {
    return mountRoot(element, PostBattleToolbar, props);
}
