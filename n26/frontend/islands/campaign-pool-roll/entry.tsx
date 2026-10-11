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
    return mountRoot(element, PoolRoll, {
        ...props,
        table: table?.value ?? props.table,
        count: { ...props.count, value: count?.value ?? props.count.value },
        rolled: { ...props.rolled, value: rolled?.value ?? props.rolled.value },
        focusedField:
            document.activeElement === count
                ? "count"
                : document.activeElement === rolled
                  ? "rolled"
                  : undefined,
    });
}
