import { mount as mountRoot } from "../../runtime/mount";
import { ThemeChoice, type ThemeChoiceProps } from "./ThemeChoice";

export function mount(element: HTMLElement, props: ThemeChoiceProps) {
    return mountRoot(element, ThemeChoice, props);
}
