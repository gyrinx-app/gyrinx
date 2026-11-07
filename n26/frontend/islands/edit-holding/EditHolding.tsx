import { useState } from "react";
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
    WorkflowPage,
    useWorkflowForm,
} from "../../ui";

type Errors = Record<string, string[]>;
type Current = { name: string; income: number | null };
export interface EditHoldingProps {
    heading: string;
    holdingName: string;
    campaignName: string;
    campaignHref: string;
    campaignsHref: string;
    detailHref: string;
    catalogueName: string;
    catalogueIncome: number;
    values: { name: string; income: string; snapshot: string };
    fields: Record<"name" | "income", { label: string; help: string }>;
    errors: Errors;
    conflict: Current | null;
    back: string;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
}
function currentValues(value: unknown): value is Current {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const data = value as Record<string, unknown>;
    return (
        typeof data.name === "string" &&
        (data.income === null || Number.isInteger(data.income))
    );
}

export function EditHolding(
    props: EditHoldingProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const [current, setCurrent] = useState(props.conflict);
    const form = useWorkflowForm({
        ...props,
        initialConflict: !!props.conflict,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                currentValues(data.current) &&
                fieldErrors(data.errors)
            ) {
                setCurrent(data.current);
                return { kind: "conflict", errors: data.errors };
            }
            if (status === 422 && fieldErrors(data.errors))
                return { kind: "invalid", errors: data.errors };
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
    const conflict = form.conflicted ? current : null;
    return (
        <WorkflowPage
            title={props.heading}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: "Campaigns", href: props.campaignsHref },
                        { label: props.campaignName, href: props.campaignHref },
                        { label: props.holdingName, href: props.detailHref },
                        { label: "Edit" },
                    ]}
                />
            }
            method="post"
            action={props.action}
            onSubmit={save}
            aria-busy={pending}
            footer={
                <FormActions>
                    {conflict ? (
                        <Button
                            type="button"
                            variant="primary"
                            onClick={() => form.review(props.action)}
                        >
                            Review current asset
                        </Button>
                    ) : (
                        <Button
                            type="submit"
                            variant="success"
                            disabled={pending}
                        >
                            {pending
                                ? "Saving…"
                                : uncertain
                                  ? "Retry save"
                                  : "Save"}
                        </Button>
                    )}
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
            <input type="hidden" name="snapshot" value={values.snapshot} />
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
                            ...(errors.snapshot ?? []),
                            ...(notice ? [notice] : []),
                        ]}
                    />
                    {!notice &&
                        !errors.__all__?.length &&
                        !errors.snapshot?.length && (
                            <p>Check the highlighted fields.</p>
                        )}
                </div>
            )}
            {conflict && (
                <div
                    role="region"
                    aria-label="Current asset details"
                    className="space-y-1"
                >
                    <p>Current name: {conflict.name || props.catalogueName}.</p>
                    <p>
                        Current income override:{" "}
                        {conflict.income === null
                            ? "None (uses catalogue income)"
                            : `${conflict.income}¢`}
                        .
                    </p>
                </div>
            )}
            <fieldset disabled={form.frozen} className="contents">
                <FormSection title="Details">
                    <p className="text-sm text-muted">
                        Catalogue entry: {props.catalogueName} · Income:{" "}
                        {props.catalogueIncome}¢.
                    </p>
                    <Field
                        label={props.fields.name.label}
                        description={props.fields.name.help}
                        descriptionPlacement="before"
                        htmlFor="asset-name"
                        errors={errors.name}
                    >
                        <Input
                            name="name"
                            maxLength={200}
                            autoComplete="off"
                            value={values.name}
                            onChange={(e) =>
                                setValues({ ...values, name: e.target.value })
                            }
                        />
                    </Field>
                    <Field
                        label={props.fields.income.label}
                        description={props.fields.income.help}
                        descriptionPlacement="before"
                        htmlFor="asset-income"
                        errors={errors.income}
                    >
                        <Input
                            name="income"
                            type="number"
                            min={0}
                            max={2147483647}
                            inputMode="numeric"
                            rightAddon="¢"
                            value={values.income}
                            onChange={(e) =>
                                setValues({ ...values, income: e.target.value })
                            }
                        />
                    </Field>
                </FormSection>
            </fieldset>
        </WorkflowPage>
    );
}
