import { mount as mountRoot } from "../../runtime/mount";
import { PostBattle, type PostBattleProps } from "./PostBattle";
export function mount(element: HTMLElement, props: PostBattleProps) {
    return mountRoot(element, PostBattle, props);
}
