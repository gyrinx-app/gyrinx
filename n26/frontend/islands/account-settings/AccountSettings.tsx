import { useId, useState } from "react";
import {
    Button,
    Field,
    FormActions,
    Input,
    NativeSelect,
    RadioCard,
    RadioCards,
} from "../../ui";

export type AccountSettingsProps = {
    actionUrl: string;
    csrfToken: string;
    errors: string[];
    fields: Array<{
        name: string;
        label: string;
        value: string;
        help: string;
        errors: string[];
        choices: Array<{ value: string; label: string; imageUrl?: string }>;
    }>;
};

export function AccountSettings({
    actionUrl,
    csrfToken,
    fields,
    errors,
}: AccountSettingsProps) {
    const id = useId();
    const [values, setValues] = useState(
        Object.fromEntries(fields.map((field) => [field.name, field.value])),
    );
    const [pending, setPending] = useState(false);
    return (
        <form
            method="post"
            action={actionUrl}
            className="space-y-5"
            onSubmit={() => setPending(true)}
        >
            <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
            <input type="hidden" name="action_save" value="1" />
            {errors.length > 0 && (
                <div role="alert">
                    {errors.map((error) => (
                        <p key={error}>{error}</p>
                    ))}
                </div>
            )}
            {fields.map((field) =>
                field.name === "selected_badge" ? (
                    <RadioCards
                        key={field.name}
                        legend={field.label}
                        errors={field.errors}
                    >
                        {field.choices.map((choice) => (
                            <RadioCard
                                key={choice.value}
                                name={field.name}
                                value={choice.value}
                                label={choice.label}
                                checked={values[field.name] === choice.value}
                                onChange={() =>
                                    setValues({
                                        ...values,
                                        [field.name]: choice.value,
                                    })
                                }
                                flair={
                                    choice.imageUrl ? (
                                        <img
                                            src={choice.imageUrl}
                                            alt=""
                                            className="inline-block h-10 w-auto max-w-20 object-contain"
                                        />
                                    ) : undefined
                                }
                            />
                        ))}
                    </RadioCards>
                ) : (
                    <Field
                        key={field.name}
                        label={field.label}
                        htmlFor={`${id}-${field.name}`}
                        description={field.help}
                        errors={field.errors}
                    >
                        {field.choices.length > 0 ? (
                            <NativeSelect
                                name={field.name}
                                value={values[field.name]}
                                onChange={(event) =>
                                    setValues({
                                        ...values,
                                        [field.name]: event.target.value,
                                    })
                                }
                            >
                                {field.choices.map((choice, index) => (
                                    <option
                                        key={`${choice.value}-${index}`}
                                        value={choice.value}
                                    >
                                        {choice.label}
                                    </option>
                                ))}
                            </NativeSelect>
                        ) : (
                            <Input
                                type="email"
                                name={field.name}
                                autoComplete="email"
                                required
                                value={values[field.name]}
                                onChange={(event) =>
                                    setValues({
                                        ...values,
                                        [field.name]: event.target.value,
                                    })
                                }
                            />
                        )}
                    </Field>
                ),
            )}
            <FormActions>
                <Button variant="success" type="submit" disabled={pending}>
                    {pending ? "Saving…" : "Save"}
                </Button>
            </FormActions>
        </form>
    );
}
