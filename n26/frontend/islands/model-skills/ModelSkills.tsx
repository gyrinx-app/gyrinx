import { type ComponentProps, type FormEvent } from "react";
import { fieldErrors } from "../../http/command";
import {
    Alert,
    Breadcrumbs,
    Button,
    ButtonLink,
    FieldErrors,
    FormActions,
    QuickSwitcher,
    RadioCard,
    RadioCards,
    TabLinks,
    UserLink,
    WorkflowPage,
    useWorkflowForm,
} from "../../ui";

type SkillGroup = {
    name: string;
    caption: string;
    options: {
        key: string;
        name: string;
        remark: string;
        summary: string;
        rating: number;
    }[];
};
export type ModelSkillsProps = {
    name: string;
    lead: string;
    gangName: string;
    gangHref: string;
    owner: ComponentProps<typeof UserLink>;
    back: string;
    switcher: ComponentProps<typeof QuickSwitcher> | null;
    collections: ComponentProps<typeof TabLinks>["tabs"];
    nothingToSelect: boolean;
    groups: SkillGroup[];
    values: {
        gang: string;
        collection: string;
        thing: string;
        thing_label: string;
        request_key: string;
    };
    errors: Record<string, string[]>;
    action: string;
    recoveryHref?: string;
    recoveryOnly?: boolean;
    removed?: boolean;
    commandHref: string;
    signInHref: string;
    csrfToken: string;
    recoveryKey: string;
    messages: {
        text: string;
        tone: "success" | "error" | "warning" | "info";
    }[];
};
export function ModelSkills(
    props: ModelSkillsProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const workflow = useWorkflowForm({
        ...props,
        optionalRecoveryFields: ["thing_label"],
        initialConflict: !!props.removed,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 409 &&
                data.code === "model_removed" &&
                fieldErrors(data.errors)
            )
                return { kind: "conflict", errors: data.errors };
            if (status === 422 && fieldErrors(data.errors))
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    function save(event: FormEvent<HTMLFormElement>) {
        if (props.recoveryHref)
            window.history.replaceState(
                window.history.state,
                "",
                props.recoveryHref,
            );
        return workflow.save(event);
    }
    if (props.recoveryOnly) {
        return (
            <WorkflowPage
                title="Recover skill selection"
                lead={props.name}
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: <UserLink {...props.owner} /> },
                            { label: props.gangName, href: props.gangHref },
                            { label: "Recover skill selection" },
                        ]}
                    />
                }
                method="post"
                action={props.action}
                onSubmit={save}
                aria-busy={workflow.pending}
                footer={
                    <FormActions>
                        {workflow.conflicted ? (
                            <Button
                                type="button"
                                variant="primary"
                                onClick={() => workflow.review(props.gangHref)}
                            >
                                Return to gang
                            </Button>
                        ) : workflow.uncertain ? (
                            <Button
                                type="submit"
                                variant="success"
                                busy={workflow.pending}
                                disabled={workflow.pending}
                            >
                                Retry save
                            </Button>
                        ) : (
                            <ButtonLink href={props.gangHref} variant="ghost">
                                Return to gang
                            </ButtonLink>
                        )}
                    </FormActions>
                }
            >
                <input
                    type="hidden"
                    name="csrfmiddlewaretoken"
                    value={props.csrfToken}
                />
                {Object.entries(workflow.values).map(([name, value]) => (
                    <input key={name} type="hidden" name={name} value={value} />
                ))}
                {props.messages.map((message, index) => (
                    <Alert key={index} tone={message.tone} dismissible>
                        {message.text}
                    </Alert>
                ))}
                <p>This model was removed from the gang.</p>
                {workflow.uncertain ? (
                    <p>
                        Submitted selection:{" "}
                        {workflow.values.thing_label ||
                            "Original skill or power"}
                        .
                    </p>
                ) : !workflow.conflicted ? (
                    <p>No unconfirmed save was found in this browser.</p>
                ) : null}
                {workflow.hasErrors && (
                    <div
                        ref={workflow.summary}
                        role="alert"
                        tabIndex={-1}
                        aria-label="Selection errors"
                    >
                        <FieldErrors
                            errors={[
                                ...Object.values(workflow.errors).flat(),
                                ...(workflow.notice ? [workflow.notice] : []),
                            ]}
                        />
                    </div>
                )}
                {workflow.notice && (
                    <ButtonLink
                        href={props.signInHref}
                        variant="ghost"
                        onClick={(event) => {
                            event.preventDefault();
                            workflow.recoverAt(
                                props.signInHref,
                                event.currentTarget.closest("form")!,
                            );
                        }}
                    >
                        Sign in
                    </ButtonLink>
                )}
            </WorkflowPage>
        );
    }
    const selectable = props.groups.some((group) => group.options.length);
    const selected = props.groups
        .flatMap((group) => group.options)
        .find((option) => option.key === workflow.values.thing);
    return (
        <WorkflowPage
            title={props.name}
            lead={props.nothingToSelect ? undefined : props.lead}
            trailing={
                props.switcher ? (
                    <QuickSwitcher {...props.switcher} />
                ) : undefined
            }
            breadcrumb={
                <Breadcrumbs
                    items={[
                        { label: <UserLink {...props.owner} /> },
                        { label: props.gangName, href: props.gangHref },
                        { label: props.name, href: props.back },
                        { label: "Skills" },
                    ]}
                />
            }
            method="post"
            action={props.action}
            onSubmit={save}
            aria-busy={workflow.pending}
            footer={
                workflow.conflicted ? (
                    <FormActions>
                        <Button
                            type="button"
                            variant="primary"
                            onClick={() => workflow.review(props.gangHref)}
                        >
                            Return to gang
                        </Button>
                    </FormActions>
                ) : selectable || workflow.uncertain ? (
                    <FormActions>
                        <ButtonLink href={props.back} variant="ghost">
                            Cancel
                        </ButtonLink>
                        <Button
                            type="submit"
                            variant="success"
                            busy={workflow.pending}
                            disabled={workflow.pending}
                        >
                            {workflow.uncertain ? "Retry save" : "Select"}
                        </Button>
                    </FormActions>
                ) : undefined
            }
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={props.csrfToken}
            />
            <input type="hidden" name="gang" value={workflow.values.gang} />
            <input
                type="hidden"
                name="collection"
                value={workflow.values.collection}
            />
            <input
                type="hidden"
                name="request_key"
                value={workflow.values.request_key}
            />
            <input type="hidden" name="thing" value={workflow.values.thing} />
            <input
                type="hidden"
                name="thing_label"
                value={workflow.values.thing_label}
            />
            {props.messages.map((message, index) => (
                <Alert key={index} tone={message.tone} dismissible>
                    {message.text}
                </Alert>
            ))}
            {workflow.hasErrors && (
                <div
                    ref={workflow.summary}
                    tabIndex={-1}
                    role="alert"
                    aria-label="Selection errors"
                >
                    <FieldErrors
                        errors={[
                            ...Object.values(workflow.errors).flat(),
                            ...(workflow.notice ? [workflow.notice] : []),
                        ]}
                    />
                    {(workflow.uncertain ||
                        (!selected && workflow.values.thing)) && (
                        <p>
                            Submitted selection:{" "}
                            {workflow.values.thing_label ||
                                selected?.name ||
                                "Skill or power"}
                            .
                        </p>
                    )}
                    {workflow.notice && (
                        <div className="mt-2 flex gap-2">
                            <ButtonLink
                                href={props.signInHref}
                                variant="ghost"
                                size="sm"
                                onClick={(event) => {
                                    event.preventDefault();
                                    workflow.recoverAt(
                                        props.signInHref,
                                        event.currentTarget.closest("form")!,
                                    );
                                }}
                            >
                                Sign in
                            </ButtonLink>
                            <ButtonLink
                                href={props.recoveryHref ?? props.action}
                                variant="ghost"
                                size="sm"
                                onClick={(event) => {
                                    event.preventDefault();
                                    workflow.recoverAt(
                                        props.recoveryHref ?? props.action,
                                        event.currentTarget.closest("form")!,
                                    );
                                }}
                            >
                                Reload form
                            </ButtonLink>
                        </div>
                    )}
                </div>
            )}
            {props.collections.length > 1 && (
                <TabLinks label="Which list" tabs={props.collections} />
            )}
            {props.nothingToSelect ? (
                <p className="text-muted">
                    This model is not graded in any skill category. A profile or
                    item that places a category in a skill list adds selections
                    here.
                </p>
            ) : !selectable ? (
                <p className="text-muted">
                    No skills or powers in these sets yet.
                </p>
            ) : (
                <fieldset disabled={workflow.frozen} className="min-w-0">
                    <div className="space-y-8">
                        {props.groups.map((group, index) => (
                            <RadioCards
                                key={`${group.name}:${index}`}
                                legend={group.name}
                                description={group.caption}
                            >
                                {group.options.map((option) => (
                                    <RadioCard
                                        key={option.key}
                                        wrap={false}
                                        name="skill-choice"
                                        value={option.key}
                                        label={option.name}
                                        description={option.remark}
                                        checked={
                                            workflow.values.thing === option.key
                                        }
                                        onChange={() =>
                                            workflow.setValues({
                                                ...workflow.values,
                                                thing: option.key,
                                                thing_label: option.name,
                                            })
                                        }
                                        details={
                                            option.summary ||
                                            !!option.rating ? (
                                                <>
                                                    {option.summary && (
                                                        <span className="block">
                                                            {option.summary}
                                                        </span>
                                                    )}
                                                    {!!option.rating && (
                                                        <span className="block text-muted">
                                                            Rating{" "}
                                                            {option.rating}¢
                                                        </span>
                                                    )}
                                                </>
                                            ) : undefined
                                        }
                                    />
                                ))}
                            </RadioCards>
                        ))}
                    </div>
                </fieldset>
            )}
        </WorkflowPage>
    );
}
