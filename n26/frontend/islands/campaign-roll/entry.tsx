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
    const active = document.activeElement;
    let focused: string | undefined;
    if (active instanceof HTMLElement && element.contains(active)) {
        if (active === rolled) focused = "rolled";
        else if (active instanceof HTMLInputElement && active.name === "table")
            focused = `table:${active.value}`;
        else if (active.matches('[type="submit"]')) focused = "submit";
        else if (active.matches("a[href]")) focused = "cancel";
    }
    return mountRoot(element, CampaignRoll, {
        ...props,
        table: table?.value ?? props.table,
        rolled: { ...props.rolled, value: rolled?.value ?? props.rolled.value },
        focused,
    });
}
