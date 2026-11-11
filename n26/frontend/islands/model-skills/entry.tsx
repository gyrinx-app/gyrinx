import { mount as mountRoot } from "../../runtime/mount";
import { ModelSkills, type ModelSkillsProps } from "./ModelSkills";
export function mount(element: HTMLElement, props: ModelSkillsProps) {
    return mountRoot(element, ModelSkills, props);
}
