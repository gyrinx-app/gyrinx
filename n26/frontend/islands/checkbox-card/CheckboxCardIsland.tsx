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
    /** The nested ticks, drawn here and inert while the card is clear. */
    items: CheckboxCardItemProps[];
    /** The server-drawn checkbox had focus when the island replaced it. */
    restoreFocus?: boolean;
    /** The server-drawn nested tick that had focus, by name and value. */
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
            // An item is inert while the card is clear, so the card takes focus.
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
        // Focus moves once, as the island replaces the server-drawn card.
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
