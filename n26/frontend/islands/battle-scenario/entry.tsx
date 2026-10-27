import { mount as mountRoot } from "../../runtime/mount";
import { BattleScenario, type BattleScenarioProps } from "./BattleScenario";
export function mount(element: HTMLElement, props: BattleScenarioProps) {
    return mountRoot(element, BattleScenario, props);
}
