import { useState, type ComponentProps, type FormEvent } from "react";
import { fieldErrors } from "../../http/command";
import {
    Alert,
    Breadcrumbs,
    Button,
    ButtonLink,
    Card,
    FieldErrors,
    GangFigures,
    ModelCard,
    ModelScreenTabs,
    QuickSwitcher,
    UserLink,
    ModelHeader,
    useWorkflowForm,
    WorkflowPage,
    FormActions,
    type ModelCardData,
} from "../../ui";

type Group = {
    key: string;
    choose: string;
    visible: boolean;
    options: { key: string; name: string; price: number; checked: boolean }[];
};
type Current = { name: string; options: string[] };
export type ModelOptionsProps = {
    name: string;
    role: string;
    owner: ComponentProps<typeof UserLink>;
    gangName: string;
    gangHref: string;
    figures: ComponentProps<typeof GangFigures>["data"] | null;
    card: ModelCardData | null;
    tabs: ComponentProps<typeof ModelScreenTabs>["tabs"];
    switcher: ComponentProps<typeof QuickSwitcher> | null;
    groups: Group[];
    values: {
        gang: string;
        selection: string;
        snapshot: string;
        request_key: string;
        selection_label: string;
    };
    errors: Record<string, string[]>;
    conflict: Current | null;
    action: string;
    recoveryHref?: string;
    recoveryOnly?: boolean;
    removed?: boolean;
    back: string;
    commandHref: string;
    signInHref: string;
    csrfToken: string;
    recoveryKey: string;
    messages: {
        text: string;
        tone: "success" | "error" | "warning" | "info";
    }[];
};
function currentOptions(value: unknown): value is Current {
    if (!value || typeof value !== "object") return false;
    const data = value as Current;
    return (
        typeof data.name === "string" &&
        Array.isArray(data.options) &&
        data.options.every((name) => typeof name === "string")
    );
}
function selectedKeys(raw: string): string[] {
    try {
        const value: unknown = JSON.parse(raw);
        return Array.isArray(value) &&
            value.every((key) => typeof key === "string")
            ? value
            : [];
    } catch {
        return [];
    }
}
export function ModelOptions(
    props: ModelOptionsProps & {
        onNavigate?: (url: string) => void;
        onReload?: () => void;
    },
) {
    const [current, setCurrent] = useState(props.conflict);
    const [removed, setRemoved] = useState(!!props.removed);
    const workflow = useWorkflowForm({
        ...props,
        initialConflict: !!props.conflict || !!props.removed,
        optionalRecoveryFields: ["selection_label"],
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
            if (
                status === 409 &&
                data.code === "model_removed" &&
                fieldErrors(data.errors)
            ) {
                setRemoved(true);
                return { kind: "conflict", errors: data.errors };
            }
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                currentOptions(data.current) &&
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
                title="Recover options"
                lead={props.name}
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: <UserLink {...props.owner} /> },
                            { label: props.gangName, href: props.gangHref },
                            { label: "Recover options" },
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
                    <Alert key={index} tone={message.tone}>
                        {message.text}
                    </Alert>
                ))}
                <p>This model was removed from the gang.</p>
                {workflow.uncertain ? (
                    <p>
                        Submitted options:{" "}
                        {workflow.values.selection_label || "Original options"}.
                    </p>
                ) : !workflow.conflicted ? (
                    <p>No unconfirmed save was found in this browser.</p>
                ) : null}
                {workflow.hasErrors && (
                    <div
                        ref={workflow.summary}
                        role="alert"
                        tabIndex={-1}
                        aria-label="Save errors"
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
    const selected = selectedKeys(workflow.values.selection);
    function toggle(group: Group, key: string, checked: boolean) {
        const exclusive = group.choose !== "any";
        const existing = exclusive
            ? selected.filter(
                  (value) =>
                      !group.options.some((option) => option.key === value),
              )
            : selected.filter((value) => value !== key);
        const next = checked && key ? [...existing, key] : existing;
        workflow.setValues({
            ...workflow.values,
            selection: JSON.stringify(next),
            selection_label: props.groups
                .flatMap((group) => group.options)
                .filter((option) => next.includes(option.key))
                .map((option) => option.name)
                .join(", "),
        });
    }
    const groups = props.groups.filter((group) => group.visible);
    return (
        <div data-busy="off">
            <ModelHeader
                title={props.name}
                lead={props.role || undefined}
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
                            { label: props.name },
                        ]}
                    />
                }
                actions={
                    props.figures ? (
                        <GangFigures data={props.figures} />
                    ) : undefined
                }
            >
                <div className="lg:max-w-1/2">
                    {props.card && (
                        <ModelCard
                            card={props.card}
                            csrfToken={props.csrfToken}
                            frozen={workflow.frozen}
                        />
                    )}
                </div>
                <ModelScreenTabs tabs={props.tabs} className="" />
            </ModelHeader>
            {props.messages.map((message, index) => (
                <Alert key={index} tone={message.tone}>
                    {message.text}
                </Alert>
            ))}
            <div className="mt-4 grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-2">
                <Card header={<h2 className="font-semibold">Options</h2>}>
                    {groups.length ||
                    workflow.hasErrors ||
                    workflow.uncertain ||
                    workflow.conflicted ? (
                        <form
                            method="post"
                            action={props.action}
                            onSubmit={save}
                            aria-busy={workflow.pending}
                        >
                            <input
                                type="hidden"
                                name="csrfmiddlewaretoken"
                                value={props.csrfToken}
                            />
                            {Object.entries(workflow.values).map(
                                ([name, value]) => (
                                    <input
                                        key={name}
                                        type="hidden"
                                        name={name}
                                        value={value}
                                    />
                                ),
                            )}
                            {workflow.hasErrors && (
                                <div
                                    ref={workflow.summary}
                                    role="alert"
                                    tabIndex={-1}
                                    aria-label="Save errors"
                                >
                                    <FieldErrors
                                        errors={[
                                            ...Object.values(
                                                workflow.errors,
                                            ).flat(),
                                            ...(workflow.notice
                                                ? [workflow.notice]
                                                : []),
                                        ]}
                                    />
                                </div>
                            )}
                            {workflow.uncertain &&
                                workflow.values.selection_label && (
                                    <p className="mb-3 text-sm text-muted">
                                        Submitted options:{" "}
                                        {workflow.values.selection_label}.
                                    </p>
                                )}
                            {workflow.conflicted && current && (
                                <div
                                    className="mb-4 text-sm"
                                    role="region"
                                    aria-label="Current model options"
                                >
                                    <p>
                                        Current options for {current.name}:{" "}
                                        {current.options.join(", ") || "None"}.
                                    </p>
                                </div>
                            )}
                            <fieldset
                                disabled={workflow.frozen}
                                className="contents"
                            >
                                {groups.map((group, index) => (
                                    <div
                                        key={group.key}
                                        className={
                                            index
                                                ? "mt-2 border-t border-box-border pt-3"
                                                : ""
                                        }
                                    >
                                        <fieldset>
                                            <legend
                                                className={`py-1 text-xs font-semibold uppercase tracking-wide text-muted ${index === 0 ? "mb-1" : ""}`}
                                            >
                                                {group.choose === "one"
                                                    ? "Choose one"
                                                    : group.choose === "any"
                                                      ? "Choose any"
                                                      : "Choose one, or none"}
                                            </legend>
                                            <div className="flex flex-col gap-1">
                                                {group.options.map((option) => (
                                                    <label
                                                        key={option.key}
                                                        className="flex min-h-9 cursor-pointer items-center gap-2 rounded-control py-0.5 hover:bg-ink-500/5"
                                                    >
                                                        <input
                                                            type={
                                                                group.choose ===
                                                                "any"
                                                                    ? "checkbox"
                                                                    : "radio"
                                                            }
                                                            name={`option-${group.key}`}
                                                            value={option.key}
                                                            checked={selected.includes(
                                                                option.key,
                                                            )}
                                                            onChange={(event) =>
                                                                toggle(
                                                                    group,
                                                                    option.key,
                                                                    event.target
                                                                        .checked,
                                                                )
                                                            }
                                                            className="size-4 shrink-0 accent-[var(--color-accent)] focus-ring"
                                                        />
                                                        <span className="min-w-0 text-sm text-ink-900 dark:text-ink-100">
                                                            {option.name}
                                                        </span>
                                                        {!!option.price && (
                                                            <span className="shrink-0 text-xs text-muted">
                                                                {option.price >
                                                                0
                                                                    ? "+"
                                                                    : ""}
                                                                {option.price}¢
                                                            </span>
                                                        )}
                                                    </label>
                                                ))}
                                                {group.choose ===
                                                    "one-or-none" && (
                                                    <label className="flex min-h-9 cursor-pointer items-center gap-2 rounded-control py-0.5 hover:bg-ink-500/5">
                                                        <input
                                                            type="radio"
                                                            name={`option-${group.key}`}
                                                            value=""
                                                            checked={
                                                                !group.options.some(
                                                                    (option) =>
                                                                        selected.includes(
                                                                            option.key,
                                                                        ),
                                                                )
                                                            }
                                                            onChange={() =>
                                                                toggle(
                                                                    group,
                                                                    "",
                                                                    false,
                                                                )
                                                            }
                                                            className="size-4 shrink-0 accent-[var(--color-accent)] focus-ring"
                                                        />
                                                        <span className="text-sm">
                                                            None
                                                        </span>
                                                    </label>
                                                )}
                                            </div>
                                        </fieldset>
                                    </div>
                                ))}
                            </fieldset>
                            <div className="mt-3 flex justify-end gap-2">
                                {workflow.conflicted ? (
                                    <Button
                                        type="button"
                                        variant="primary"
                                        onClick={() =>
                                            workflow.review(
                                                removed
                                                    ? props.gangHref
                                                    : props.action,
                                            )
                                        }
                                    >
                                        {removed
                                            ? "Return to gang"
                                            : "Review current options"}
                                    </Button>
                                ) : (
                                    <Button
                                        type="submit"
                                        variant="success"
                                        size="sm"
                                        busy={workflow.pending}
                                        disabled={workflow.pending}
                                    >
                                        {workflow.uncertain
                                            ? "Retry save"
                                            : "Save options"}
                                    </Button>
                                )}
                                {workflow.notice && (
                                    <ButtonLink
                                        href={props.signInHref}
                                        variant="ghost"
                                        size="sm"
                                        onClick={(event) => {
                                            event.preventDefault();
                                            workflow.recoverAt(
                                                props.signInHref,
                                                event.currentTarget.closest(
                                                    "form",
                                                )!,
                                            );
                                        }}
                                    >
                                        Sign in
                                    </ButtonLink>
                                )}
                                {workflow.notice && (
                                    <ButtonLink
                                        href={
                                            props.recoveryHref ?? props.action
                                        }
                                        variant="ghost"
                                        size="sm"
                                        onClick={(event) => {
                                            event.preventDefault();
                                            workflow.recoverAt(
                                                props.recoveryHref ??
                                                    props.action,
                                                event.currentTarget.closest(
                                                    "form",
                                                )!,
                                            );
                                        }}
                                    >
                                        Reload form
                                    </ButtonLink>
                                )}
                            </div>
                        </form>
                    ) : (
                        <p className="text-muted">
                            {props.name}'s profile offers no options to choose.
                        </p>
                    )}
                </Card>
            </div>
        </div>
    );
}
