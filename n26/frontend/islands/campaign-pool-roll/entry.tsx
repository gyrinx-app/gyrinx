import { mount as mountRoot } from "../../runtime/mount";
import { PoolRoll, type PoolRollProps } from "./PoolRoll";

export function mount(element: HTMLElement, props: PoolRollProps) {
    // Preserve edits and focus made before the module finished loading.
    const count = element.querySelector<HTMLInputElement>(
        'input[name="count"]',
    );
    const rolled = element.querySelector<HTMLInputElement>(
        'input[name="rolled"]',
    );
    const table = element.querySelector<HTMLInputElement>(
        'input[name="table"]:checked, input[type="hidden"][name="table"]',
    );
    const duplicate = element.querySelector<HTMLInputElement>(
        'input[name="avoid_duplicates"]',
    );
    const active = document.activeElement;
    return mountRoot(element, PoolRoll, {
        ...props,
        avoidDuplicates: props.avoidDuplicates
            ? {
                  ...props.avoidDuplicates,
                  checked: duplicate?.checked ?? props.avoidDuplicates.checked,
              }
            : props.avoidDuplicates,
        table: table?.value ?? props.table,
        count: { ...props.count, value: count?.value ?? props.count.value },
        rolled: { ...props.rolled, value: rolled?.value ?? props.rolled.value },
        focusedField:
            active === count
                ? "count"
                : active === rolled
                  ? "rolled"
                  : active instanceof HTMLInputElement &&
                      active.name === "table" &&
                      element.contains(active)
                    ? `table:${active.value}`
                    : undefined,
    });
}
