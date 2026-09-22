import { useId, useState } from "react";
import { Field, Input, Switch } from "../../ui";

type TextFieldProps = {
    htmlName: string;
    label: string;
    helpText: string;
    value: string;
    errors: string[];
};

type SwitchFieldProps = Omit<TextFieldProps, "value"> & {
    value: boolean;
};

export type ModifierNamingProps = {
    carrier: string;
    name: TextFieldProps;
    reusable: SwitchFieldProps;
};

export function ModifierNaming({
    carrier,
    name: nameField,
    reusable: reusableField,
}: ModifierNamingProps) {
    const nameId = useId();
    const reusableId = useId();
    const [name, setName] = useState(nameField.value);
    const [reusable, setReusable] = useState(reusableField.value);
    const typed = name.trim();
    const preview =
        typed || (reusable ? "what it does" : `${carrier}: what it does`);

    return (
        <div className="space-y-5">
            <Field
                label={nameField.label}
                htmlFor={nameId}
                description={nameField.helpText}
                errors={nameField.errors}
            >
                <Input
                    id={nameId}
                    type="text"
                    name={nameField.htmlName}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                />
            </Field>
            <div>
                <Field
                    label={reusableField.label}
                    htmlFor={reusableId}
                    description={reusableField.helpText}
                    errors={reusableField.errors}
                    variant="toggle"
                >
                    <Switch
                        id={reusableId}
                        name={reusableField.htmlName}
                        checked={reusable}
                        onCheckedChange={setReusable}
                        label={reusableField.label}
                    />
                </Field>
                <p className="mt-1 text-xs text-muted">
                    Will be named{" "}
                    <span className="font-medium text-ink-900 dark:text-ink-100">
                        {preview}
                    </span>
                </p>
            </div>
        </div>
    );
}
