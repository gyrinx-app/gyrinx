import { mount as mountRoot } from "../../runtime/mount";
import { BattleEditor, type BattleEditorProps } from "./BattleEditor";
export function mount(element: HTMLElement, props: BattleEditorProps) {
    return mountRoot(element, BattleEditor, props);
}
