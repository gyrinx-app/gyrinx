import { useId, useState } from "react";
import { Button, Field, FormActions, Input, Link } from "../../ui";

export type AccountPasswordProps = {
    actionUrl: string;
    csrfToken: string;
    returnUrl: string;
    resetUrl: string;
    errors: string[];
    fields: Array<{
        name: string;
        label: string;
        autocomplete: string;
        errors: string[];
        help: string;
    }>;
};

export function AccountPassword({
    actionUrl,
    csrfToken,
    returnUrl,
    resetUrl,
    fields,
    errors,
}: AccountPasswordProps) {
    const id = useId();
    const [visible, setVisible] = useState(false);
    const [pending, setPending] = useState(false);
    const [values, setValues] = useState<Record<string, string>>({});
    const mismatch =
        !!values.password2 && values.password1 !== values.password2;
    return (
        <form
            method="post"
            action={actionUrl}
            className="space-y-5"
            onSubmit={(event) => {
                if (mismatch) event.preventDefault();
                else setPending(true);
            }}
        >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="next" value={returnUrl} />
            {errors.length > 0 && (
                <div role="alert">
                    {errors.map((error) => (
                        <p key={error}>{error}</p>
                    ))}
                </div>
            )}
            {fields.map((field) => (
                <Field
                    key={field.name}
                    htmlFor={`${id}-${field.name}`}
                    label={field.label}
                    description={field.help}
                    errors={[
                        ...field.errors,
                        ...(field.name === "password2" && mismatch
                            ? ["The new passwords must match."]
                            : []),
                    ]}
                >
                    <Input
                        type={visible ? "text" : "password"}
                        name={field.name}
                        autoComplete={field.autocomplete}
                        required
                        value={values[field.name] ?? ""}
                        onChange={(event) =>
                            setValues({
                                ...values,
                                [field.name]: event.target.value,
                            })
                        }
                    />
                </Field>
            ))}
            <Button
                variant="text"
                onClick={() => setVisible(!visible)}
                aria-pressed={visible}
            >
                {visible ? "Hide passwords" : "Show passwords"}
            </Button>
            <FormActions>
                <Button
                    type="submit"
                    variant="success"
                    disabled={pending || mismatch}
                >
                    {pending ? "Saving…" : "Save password"}
                </Button>
                <Link href={resetUrl}>Reset password</Link>
            </FormActions>
        </form>
    );
}
