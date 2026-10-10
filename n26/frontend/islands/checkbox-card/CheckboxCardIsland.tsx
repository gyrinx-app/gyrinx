import { useLayoutEffect, useRef, useState } from "react";
import { CheckboxCard, CheckboxCardItem } from "../../ui";

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
}: CheckboxCardIslandProps) {
    const frame = useRef<HTMLDivElement>(null);
    const [checked, setChecked] = useState(initiallyChecked);
    useLayoutEffect(() => {
        if (!restoreFocus) return;
        frame.current
            ?.querySelector<HTMLInputElement>("label input[type='checkbox']")
            ?.focus();
    }, [restoreFocus]);
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
                        <span className="shrink-0 text-sm tabular-nums text-muted">
                            {meta}
                        </span>
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
