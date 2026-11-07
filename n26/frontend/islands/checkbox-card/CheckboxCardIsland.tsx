import { useLayoutEffect, useRef, useState } from "react";
import { CheckboxCard, CheckboxCardItem, CheckboxCardMeta } from "../../ui";

export type CheckboxCardItemProps = {
    name: string;
    value: string;
    label: string;
    checked: boolean;
    meta: string;
};

export type CheckboxCardIslandProps = {
    name: string;
    value: string;
    checked: boolean;
    label: string;
    description: string;
    className: string;
    /** A figure beside the label, as text. */
    meta: string;
    /** Nested checkbox options, inert while the card is unticked. */
    items: CheckboxCardItemProps[];
    /** Whether the native checkbox had focus before mount. */
    restoreFocus?: boolean;
    /** Name and value of the nested checkbox focused before mount. */
    focusItem?: { name: string; value: string } | null;
};

export function CheckboxCardIsland({
    name,
    value,
    checked: initiallyChecked,
    label,
    description,
    className,
    meta,
    items,
    restoreFocus = false,
    focusItem = null,
}: CheckboxCardIslandProps) {
    const frame = useRef<HTMLDivElement>(null);
    const [checked, setChecked] = useState(initiallyChecked);
    useLayoutEffect(() => {
        const card = frame.current?.querySelector<HTMLInputElement>(
            "label input[type='checkbox']",
        );
        if (restoreFocus) {
            card?.focus();
        } else if (focusItem) {
            // The unticked card makes its nested controls inert, so focus
            // its enabling checkbox.
            const item = initiallyChecked
                ? Array.from(
                      frame.current?.querySelectorAll<HTMLInputElement>(
                          "input[type='checkbox']",
                      ) ?? [],
                  ).find(
                      (input) =>
                          input.name === focusItem.name &&
                          input.value === focusItem.value,
                  )
                : undefined;
            (item ?? card)?.focus();
        }
        // Restore focus once when replacing the server-rendered controls.
    }, []);
    return (
        <div ref={frame} className="contents">
            <CheckboxCard
                checked={checked}
                onCheckedChange={setChecked}
                label={label}
                description={description || undefined}
                className={className}
                name={name}
                value={value}
                meta={
                    meta ? (
                        <CheckboxCardMeta>{meta}</CheckboxCardMeta>
                    ) : undefined
                }
            >
                {items.length
                    ? items.map((item) => (
                          <CheckboxCardItem
                              key={`${item.name}:${item.value}`}
                              name={item.name}
                              value={item.value}
                              label={item.label}
                              defaultChecked={item.checked}
                              meta={item.meta}
                          />
                      ))
                    : null}
            </CheckboxCard>
        </div>
    );
}
