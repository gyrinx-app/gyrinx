import { useState } from "react";
import { Field, Input } from "../../ui";
export type AccountLoginNameProps = {
    id: string;
    name: string;
    label: string;
    value: string;
    errors: string[];
    required: boolean;
    autocomplete: string;
};
export function AccountLoginName(props: AccountLoginNameProps) {
    const [value, setValue] = useState(props.value);
    const warning = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
    return (
        <Field htmlFor={props.id} label={props.label} errors={props.errors}>
            <Input
                name={props.name}
                value={value}
                autoComplete={props.autocomplete}
                required={props.required}
                onChange={(event) => setValue(event.target.value)}
            />
            {warning && (
                <p
                    role="status"
                    className="text-sm text-amber-700 dark:text-amber-400"
                >
                    Use your username to sign in.
                </p>
            )}
        </Field>
    );
}
