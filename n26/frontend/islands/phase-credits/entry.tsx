import { mount as mountRoot } from "../../runtime/mount";
import { PhaseCredits, type PhaseCreditsProps } from "./PhaseCredits";
export function mount(element: HTMLElement, props: PhaseCreditsProps) {
    return mountRoot(element, PhaseCredits, props);
}
