import { useLayoutEffect, useRef, useState } from "react";
import { CheckboxCard } from "../../ui";

export type CheckboxCardIslandProps = {
    name: string;
    value: string;
    checked: boolean;
    label: string;
    description: string;
    className: string;
    /** The server-drawn checkbox had focus when the island replaced it. */
    restoreFocus?: boolean;
};

// A header-only card. A card with nested controls is composed in React by the
// island that owns its form, so this one never takes server-drawn children.
export function CheckboxCardIsland({
    name,
    value,
    checked: initiallyChecked,
    label,
    description,
    className,
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
            />
        </div>
    );
}
