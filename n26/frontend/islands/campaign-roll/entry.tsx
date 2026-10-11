import { mount as mountRoot } from "../../runtime/mount";
import { CampaignRoll, type CampaignRollProps } from "./CampaignRoll";

export function mount(element: HTMLElement, props: CampaignRollProps) {
    // Keep a choice, a typed roll and focus made before the module loaded.
    const rolled = element.querySelector<HTMLInputElement>(
        'input[name="rolled"]',
    );
    const table = element.querySelector<HTMLInputElement>(
        'input[name="table"]:checked',
    );
    return mountRoot(element, CampaignRoll, {
        ...props,
        table: table?.value ?? props.table,
        rolled: { ...props.rolled, value: rolled?.value ?? props.rolled.value },
        focused: rolled !== null && document.activeElement === rolled,
    });
}
