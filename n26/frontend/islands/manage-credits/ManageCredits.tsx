import { type ComponentProps, useState } from "react";
import { fieldErrors } from "../../http/command";
import {
    Breadcrumbs,
    Button,
    ButtonLink,
    Field,
    FieldErrors,
    FormActions,
    FormSection,
    Input,
    RadioCard,
    RadioCards,
    UserLink,
    WorkflowPage,
    useWorkflowForm,
} from "../../ui";

type Errors = Record<string, string[]>;
export interface ManageCreditsProps {
    gangName: string;
    balance: number;
    gangHref: string;
    owner: ComponentProps<typeof UserLink>;
    historyHref: string;
    directions: Array<{ value: string; label: string; description: string }>;
    values: {
        direction: string;
        amount: string | number;
        note: string;
        request_key: string;
    };
    errors: Errors;
    noteHelp: string;
    back: string;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
}

export function ManageCredits(
    props: ManageCreditsProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const [balance, setBalance] = useState(props.balance);
    const form = useWorkflowForm({
        ...props,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                (status === 422 || status === 409) &&
                fieldErrors(data.errors) &&
                typeof data.balance === "number"
            ) {
                setBalance(data.balance);
                return { kind: "invalid", errors: data.errors };
            }
            return null;
        },
    });
    const {
        values,
        setValues,
        errors,
        pending,
        uncertain,
        notice,
        summary,
        hasErrors,
        save,
    } = form;
    return (
        <WorkflowPage
            title="Manage credits"
            lead={`${props.gangName} has ${balance}¢.`}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: <UserLink {...props.owner} /> },
                        { label: props.gangName, href: props.gangHref },
                        { label: "Manage credits" },
                    ]}
                />
            }
            actions={
                props.historyHref ? (
                    <ButtonLink href={props.historyHref} size="sm">
                        Credit history
                    </ButtonLink>
                ) : undefined
            }
            method="post"
            action={props.action}
            onSubmit={save}
            aria-busy={pending}
            footer={
                <FormActions>
                    <Button
                        type="submit"
                        variant="success"
                        disabled={pending}
                        busy={pending}
                    >
                        {uncertain ? "Retry save" : "Save"}
                    </Button>
                    <ButtonLink href={props.back} variant="ghost">
                        Cancel
                    </ButtonLink>
                </FormActions>
            }
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            <input type="hidden" name="back" value={props.back} />
            <input
                type="hidden"
                name="request_key"
                value={values.request_key}
            />
            {hasErrors && (
                <div
                    ref={summary}
                    tabIndex={-1}
                    role="alert"
                    aria-label="Save errors"
                >
                    <FieldErrors
                        errors={[
                            ...(errors.__all__ ?? []),
                            ...(errors.request_key ?? []),
                            ...(notice ? [notice] : []),
                        ]}
                    />
                    {!notice &&
                        !errors.__all__?.length &&
                        !errors.request_key?.length && (
                            <p>Check the highlighted fields.</p>
                        )}
                </div>
            )}
            <fieldset disabled={form.frozen} className="contents">
                <FormSection title="The change">
                    <RadioCards
                        legend="Add or remove *"
                        min="12rem"
                        errors={errors.direction}
                    >
                        {props.directions.map((choice) => (
                            <RadioCard
                                key={choice.value}
                                name="direction"
                                {...choice}
                                checked={values.direction === choice.value}
                                onChange={() =>
                                    setValues({
                                        ...values,
                                        direction: choice.value,
                                    })
                                }
                            />
                        ))}
                    </RadioCards>
                    <Field
                        label="Credits *"
                        htmlFor="credits-amount"
                        errors={errors.amount}
                    >
                        <Input
                            name="amount"
                            type="number"
                            min="1"
                            max="1000000"
                            inputMode="numeric"
                            required
                            value={values.amount}
                            onChange={(e) =>
                                setValues({ ...values, amount: e.target.value })
                            }
                            rightAddon={
                                <span
                                    className="text-sm text-muted"
                                    aria-hidden="true"
                                >
                                    ¢
                                </span>
                            }
                        />
                    </Field>
                    <Field
                        label="Note"
                        htmlFor="credits-note"
                        description={props.noteHelp}
                        descriptionPlacement="before"
                        errors={errors.note}
                    >
                        <Input
                            name="note"
                            maxLength={255}
                            autoComplete="off"
                            value={values.note}
                            onChange={(e) =>
                                setValues({ ...values, note: e.target.value })
                            }
                        />
                    </Field>
                </FormSection>
            </fieldset>
        </WorkflowPage>
    );
}
