import { type ComponentProps, useState } from "react";
import { fieldErrors, type FormErrors } from "../../http/command";
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

type FieldName = "label_singular" | "label_plural" | "display_group";
type Current = Record<
    FieldName | "ownership" | "ownershipLabel" | "fixedReason",
    string
>;
export interface EditAssetTypeProps {
    heading: string;
    campaignName: string;
    campaignHref: string;
    campaignsHref: string;
    owner: ComponentProps<typeof UserLink>;
    back: string;
    action: string;
    commandHref: string;
    csrfToken: string;
    recoveryKey: string;
    values: Record<FieldName | "ownership" | "snapshot", string>;
    fields: Record<FieldName | "ownership", { label: string; help: string }>;
    ownershipNote: string;
    ownerships: Array<{ value: string; label: string; description: string }>;
    errors: FormErrors;
    conflict: Current | null;
}
function currentValues(value: unknown): value is Current {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const data = value as Record<string, unknown>;
    return [
        "label_singular",
        "label_plural",
        "display_group",
        "ownership",
        "ownershipLabel",
        "fixedReason",
    ].every((name) => typeof data[name] === "string");
}

export function EditAssetType(
    props: EditAssetTypeProps & {
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
    const conflict = form.conflicted ? current : null;
    const { values, setValues, errors, pending, uncertain, notice, summary } =
        form;
    return (
        <WorkflowPage
            title={props.heading}
            lead={`Only ${props.campaignName} has this asset type.`}
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: <UserLink {...props.owner} /> },
                        { label: "Campaigns", href: props.campaignsHref },
                        { label: props.campaignName, href: props.campaignHref },
                        { label: "Asset types", href: props.back },
                        { label: props.heading },
                    ]}
                />
            }
            method="post"
            action={props.action}
            onSubmit={form.save}
            aria-busy={pending}
            footer={
                <FormActions>
                    {conflict ? (
                        <Button
                            type="button"
                            variant="primary"
                            onClick={() => form.review(props.action)}
                        >
                            Review current asset type
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
                                  : "Save asset type"}
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
            {form.hasErrors && (
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
                    aria-label="Current asset type details"
                    className="space-y-1"
                >
                    <p>Current label: {conflict.label_singular}.</p>
                    <p>
                        Current plural label:{" "}
                        {conflict.label_plural || "Automatic"}.
                    </p>
                    <p>
                        Current display group:{" "}
                        {conflict.display_group || "None"}.
                    </p>
                    <p>
                        Current ownership: {conflict.ownershipLabel}.{" "}
                        {conflict.fixedReason}
                    </p>
                </div>
            )}
            <fieldset disabled={form.frozen} className="contents">
                <div className="space-y-8">
                    <FormSection title="The asset type">
                        {(
                            [
                                "label_singular",
                                "label_plural",
                                "display_group",
                            ] as const
                        ).map((name) => (
                            <Field
                                key={name}
                                label={`${props.fields[name].label}${name === "label_singular" ? " *" : ""}`}
                                description={props.fields[name].help}
                                descriptionPlacement="before"
                                htmlFor={`asset-type-${name}`}
                                errors={errors[name]}
                            >
                                <Input
                                    name={name}
                                    autoComplete="off"
                                    maxLength={200}
                                    required={name === "label_singular"}
                                    value={values[name]}
                                    onChange={(event) =>
                                        setValues({
                                            ...values,
                                            [name]: event.target.value,
                                        })
                                    }
                                />
                            </Field>
                        ))}
                    </FormSection>
                    <FormSection title="Ownership">
                        {props.ownershipNote ? (
                            <>
                                <p className="text-sm">{props.ownershipNote}</p>
                                <input
                                    type="hidden"
                                    name="ownership"
                                    value={values.ownership}
                                />
                            </>
                        ) : (
                            <RadioCards
                                legend="Ownership *"
                                errors={errors.ownership}
                            >
                                {props.ownerships.map((choice) => (
                                    <RadioCard
                                        key={choice.value}
                                        name="ownership"
                                        {...choice}
                                        checked={
                                            values.ownership === choice.value
                                        }
                                        onChange={() =>
                                            setValues({
                                                ...values,
                                                ownership: choice.value,
                                            })
                                        }
                                    />
                                ))}
                            </RadioCards>
                        )}
                    </FormSection>
                </div>
            </fieldset>
        </WorkflowPage>
    );
}
