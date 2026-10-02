import { useState } from "react";
import { Switch } from "../../ui";

export type FormSwitchProps = {
    name: string;
    value: string;
    checked: boolean;
    disabled: boolean;
    accent: boolean;
    size: "xs" | "sm" | "md" | "lg" | "xl" | "2xl";
    className: string;
    id: string;
};

export function FormSwitch({
    name,
    value,
    checked: initiallyChecked,
    disabled,
    accent,
    size,
    className,
    id,
}: FormSwitchProps) {
    const [checked, setChecked] = useState(initiallyChecked);
    return (
        <Switch
            embedded
            id={id || undefined}
            name={name}
            value={value}
            checked={checked}
            disabled={disabled}
            accent={accent}
            size={size}
            className={className}
            label=""
            onCheckedChange={setChecked}
        />
    );
}
