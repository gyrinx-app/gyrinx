import { useEffect, useRef } from "react";
import {
    ActionBar,
    Alert,
    Breadcrumbs,
    Button,
    FormActions,
    Icon,
    Spinner,
    WorkflowLayout,
} from "../../ui";
import { ModelResults } from "./ModelResults";
import { MissionResults } from "./MissionResults";
import { value, type PostBattleProps } from "./types";
import { useReportDraft } from "./useReportDraft";
export type { PostBattleProps } from "./types";
export function PostBattle(props: PostBattleProps) {
    const form = useReportDraft(props);
    const d = form.display;
    const dock = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (!dock.current) return;
        const measure = () =>
            document.documentElement.style.setProperty(
                "--n26-battle-actions-height",
                `${dock.current?.getBoundingClientRect().height || 0}px`,
            );
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(dock.current);
        return () => {
            observer.disconnect();
            document.documentElement.style.removeProperty(
                "--n26-battle-actions-height",
            );
        };
    }, []);
    const selected = d.models.filter(
        (model) => value(form, `${model.prefix}-participated`) === "on",
    );
    const eligible = selected.filter((model) => model.xpAvailable);
    const toolbarLabel = (one: string, many: string) =>
        (selected.length === 1 ? one : many).replace(
            "{n}",
            String(selected.length),
        );
    const bulk = (amount: number) => {
        for (const model of eligible) {
            const number = Number(value(form, `${model.prefix}-xp`) || 0);
            if (!Number.isInteger(number)) return;
        }
        for (const model of eligible)
            form.change(
                `${model.prefix}-xp`,
                String(
                    Math.max(
                        0,
                        Number(value(form, `${model.prefix}-xp`) || 0) + amount,
                    ),
                ),
            );
    };
    const validXp = eligible.every((model) =>
        Number.isInteger(Number(value(form, `${model.prefix}-xp`) || 0)),
    );
    return (
        <div data-busy="off">
            <WorkflowLayout
                footer={null}
                fullWidth
                title={d.title}
                lead={d.lead}
                breadcrumb={<Breadcrumbs items={d.breadcrumbs} />}
                actions={
                    <p
                        role="status"
                        aria-live="polite"
                        className="inline-flex min-w-44 items-center justify-start sm:justify-end gap-2 text-sm text-muted"
                    >
                        <span className="inline-flex size-4">
                            {form.pending && <Spinner label="Saving draft" />}
                        </span>
                        {form.uncertain
                            ? "Save unconfirmed"
                            : form.dirty
                              ? "Unsaved changes"
                              : `Draft saved ${d.savedAt}`}
                    </p>
                }
            >
                <form
                    ref={form.form}
                    method="post"
                    action={props.action}
                    id="post-battle-form"
                    noValidate
                    onSubmit={(event) => {
                        event.preventDefault();
                        void form.send("save");
                    }}
                    className="space-y-6"
                    data-busy="off"
                >
                    {props.messages.map((message, index) => (
                        <Alert
                            key={index}
                            tone={
                                message.level >= 40
                                    ? "error"
                                    : message.level >= 30
                                      ? "warning"
                                      : message.level >= 25
                                        ? "success"
                                        : "info"
                            }
                        >
                            {message.text}
                        </Alert>
                    ))}
                    {d.correcting && !d.applied && (
                        <div className="border border-box-border bg-surface p-4">
                            <p className="font-semibold">
                                Correcting recorded results
                            </p>
                            <p className="mt-1 text-sm text-muted">
                                Enter the corrected awards for this battle. Only
                                the difference from the previous report is
                                applied to today's totals.
                            </p>
                            <a
                                className="mt-2 inline-block text-sm text-accent"
                                href={d.receiptHref}
                            >
                                View recorded results
                            </a>
                        </div>
                    )}
                    {(form.notice || form.conflict || d.errors.length > 0) && (
                        <div ref={form.summary} tabIndex={-1}>
                            <Alert tone="error" dismissible={false}>
                                <h2 className="font-semibold">
                                    Check these results
                                </h2>
                                {form.notice &&
                                    form.notice !== d.errors.join(" ") && (
                                        <p>{form.notice}</p>
                                    )}
                                {d.errors.length > 0 && (
                                    <ul className="mt-2 list-disc space-y-1 pl-5">
                                        {d.errors.map((error) => (
                                            <li key={error}>{error}</li>
                                        ))}
                                    </ul>
                                )}
                                {form.notice && !form.conflict && (
                                    <div className="mt-3 flex flex-wrap gap-2">
                                        {form.uncertain && (
                                            <Button
                                                busy={!!form.pending}
                                                disabled={!!form.pending}
                                                onClick={() =>
                                                    void form.send("autosave")
                                                }
                                            >
                                                Retry save
                                            </Button>
                                        )}
                                        <Button
                                            variant="ghost"
                                            disabled={!!form.pending}
                                            onClick={form.reloadForRecovery}
                                        >
                                            Reload to sign in or recover
                                        </Button>
                                    </div>
                                )}
                                {form.uncertain && (
                                    <details className="mt-3">
                                        <summary className="cursor-pointer">
                                            Review unconfirmed model entries
                                        </summary>
                                        <ul>
                                            {form.unconfirmedModels.map(
                                                (model) => (
                                                    <li key={model.id}>
                                                        {model.name}:{" "}
                                                        {model.participated
                                                            ? "Took part"
                                                            : "Did not take part"}
                                                        ; {model.xp} XP
                                                        {model.note
                                                            ? `; Note: ${model.note}`
                                                            : ""}
                                                    </li>
                                                ),
                                            )}
                                        </ul>
                                    </details>
                                )}
                                {form.conflict && (
                                    <div className="mt-3 space-y-3">
                                        <p>
                                            {form.conflict.applied
                                                ? "These results have already been applied. Your entries remain below."
                                                : `Your entries remain below. The latest saved draft has revision ${form.conflict.revision}.`}
                                        </p>
                                        <details>
                                            <summary className="cursor-pointer">
                                                Compare latest saved changes
                                            </summary>
                                            <dl>
                                                {form.conflict.preview.rows.map(
                                                    (row) => (
                                                        <div key={row.id}>
                                                            <dt>{row.label}</dt>
                                                            <dd>{row.value}</dd>
                                                        </div>
                                                    ),
                                                )}
                                            </dl>
                                            <ul>
                                                {form.conflict.preview.models.map(
                                                    (model) => (
                                                        <li key={model.id}>
                                                            {model.name}:{" "}
                                                            {model.lines.join(
                                                                "; ",
                                                            )}
                                                        </li>
                                                    ),
                                                )}
                                            </ul>
                                        </details>
                                        {form.conflict.applied ? (
                                            <div className="space-y-2">
                                                <a
                                                    className="text-accent underline"
                                                    href={
                                                        form.conflict
                                                            .receiptHref
                                                    }
                                                >
                                                    View recorded results
                                                </a>
                                                <p>
                                                    Open the recorded results to
                                                    start a correction.
                                                </p>
                                            </div>
                                        ) : (
                                            <Button onClick={form.reviewLatest}>
                                                Use latest saved draft
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </Alert>
                        </div>
                    )}
                    <fieldset disabled={form.frozen} className="contents">
                        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
                            <div className="min-w-0 space-y-8">
                                <MissionResults form={form} />
                                <section
                                    aria-labelledby="models-heading"
                                    className="space-y-3"
                                >
                                    <div>
                                        <h2
                                            id="models-heading"
                                            className="text-lg font-semibold"
                                        >
                                            Model results
                                        </h2>
                                        <p className="mt-1 text-sm text-muted">
                                            Tick the models that took part.
                                            Unused reinforcements do not earn XP
                                            for taking part.
                                        </p>
                                    </div>
                                    <div className="sticky top-[var(--n26-sticky-top)] z-10">
                                        <ActionBar className="border border-box-border bg-ink-100 p-3 dark:bg-ink-900">
                                            <p
                                                role="status"
                                                aria-live="polite"
                                                className="mr-auto w-full text-sm font-semibold sm:w-auto"
                                            >
                                                {toolbarLabel(
                                                    d.toolbar.countOne,
                                                    d.toolbar.countMany,
                                                )}
                                            </p>
                                            <Button
                                                disabled={
                                                    !d.models.length ||
                                                    selected.length ===
                                                        d.models.length
                                                }
                                                onClick={() => {
                                                    for (const model of d.models)
                                                        form.change(
                                                            `${model.prefix}-participated`,
                                                            "on",
                                                        );
                                                }}
                                            >
                                                Mark all attended
                                            </Button>
                                            <Button
                                                disabled={
                                                    !eligible.length ||
                                                    !validXp ||
                                                    eligible.every(
                                                        (model) =>
                                                            Number(
                                                                value(
                                                                    form,
                                                                    `${model.prefix}-xp`,
                                                                ) || 0,
                                                            ) <= 0,
                                                    )
                                                }
                                                aria-label={toolbarLabel(
                                                    d.toolbar.minusOne,
                                                    d.toolbar.minusMany,
                                                )}
                                                onClick={() => bulk(-1)}
                                            >
                                                −1 XP
                                            </Button>
                                            <Button
                                                disabled={
                                                    !eligible.length || !validXp
                                                }
                                                aria-label={toolbarLabel(
                                                    d.toolbar.plusOne,
                                                    d.toolbar.plusMany,
                                                )}
                                                onClick={() => bulk(1)}
                                            >
                                                +1 XP
                                            </Button>
                                        </ActionBar>
                                    </div>
                                    <div className="space-y-4">
                                        {d.models.map((model) => (
                                            <ModelResults
                                                key={model.id}
                                                model={model}
                                                form={form}
                                            />
                                        ))}
                                        {!d.models.length && (
                                            <p className="text-sm text-muted">
                                                No models on this gang's roster.
                                            </p>
                                        )}
                                    </div>
                                </section>
                            </div>
                            <aside
                                className="space-y-4 lg:sticky lg:top-20"
                                aria-labelledby="changes-heading"
                            >
                                <div
                                    className="border border-box-border bg-ink-100 p-4 dark:bg-ink-900"
                                    aria-busy={!!form.pending || form.dirty}
                                >
                                    <h2
                                        id="changes-heading"
                                        className="text-lg font-semibold"
                                    >
                                        Changes to apply
                                    </h2>
                                    <p className="mt-2 text-sm text-muted">
                                        These changes take effect when you apply
                                        the results.
                                    </p>
                                    <dl className="mt-4 space-y-3 text-sm">
                                        {d.preview.rows.map((row) => (
                                            <div
                                                key={row.id}
                                                className="flex min-w-0 justify-between gap-3"
                                            >
                                                <dt className="min-w-0 break-words">
                                                    {row.label}
                                                </dt>
                                                <dd className="min-w-0 break-words text-right tabular-nums">
                                                    {row.value}
                                                </dd>
                                            </div>
                                        ))}
                                    </dl>
                                    <ul className="mt-4 space-y-3 text-sm">
                                        {d.preview.models.map((model) => (
                                            <li key={model.id}>
                                                <p className="font-medium">
                                                    {model.name}
                                                </p>
                                                {model.lines.map(
                                                    (line, index) => (
                                                        <p
                                                            key={index}
                                                            className="text-muted tabular-nums"
                                                        >
                                                            {line}
                                                        </p>
                                                    ),
                                                )}
                                                {model.error && (
                                                    <p className="text-red-700 dark:text-red-300">
                                                        {model.error}
                                                    </p>
                                                )}
                                            </li>
                                        ))}
                                    </ul>
                                    <Button
                                        className="mt-4 w-full"
                                        busy={form.pending === "check"}
                                        disabled={!!form.pending}
                                        onClick={() => void form.send("check")}
                                    >
                                        Check changes
                                    </Button>
                                    <p
                                        role="status"
                                        aria-live="polite"
                                        className="mt-4 flex items-start gap-2 border-t border-box-border pt-3 text-xs text-muted"
                                    >
                                        <Icon
                                            name={
                                                form.notice
                                                    ? "triangle-alert"
                                                    : form.pending || form.dirty
                                                      ? "loader-circle"
                                                      : "check-check"
                                            }
                                            className="size-4 shrink-0"
                                        />
                                        {form.notice
                                            ? "Preview needs checking."
                                            : form.pending || form.dirty
                                              ? "Updating changes to apply."
                                              : "Preview is up to date."}
                                    </p>
                                </div>
                            </aside>
                        </div>
                    </fieldset>
                    <div
                        ref={dock}
                        className="n26-battle-actions"
                        data-battle-actions=""
                        aria-label="Save post-battle results"
                    >
                        <div className="n26-site-container space-y-3">
                            <div className="border border-amber-400 bg-amber-50 px-3 py-2 dark:border-amber-700 dark:bg-amber-950">
                                <label
                                    className="flex min-h-11 items-center gap-3"
                                    htmlFor="participation-check"
                                >
                                    <input
                                        id="participation-check"
                                        name="participation_confirmed"
                                        type="checkbox"
                                        aria-label="I have checked which models took part."
                                        aria-required="true"
                                        aria-describedby="participation-help"
                                        className="size-5 shrink-0 accent-[var(--color-accent)]"
                                        disabled={form.frozen}
                                        checked={
                                            value(
                                                form,
                                                "participation_confirmed",
                                            ) === "on"
                                        }
                                        onChange={(event) =>
                                            form.change(
                                                "participation_confirmed",
                                                event.currentTarget.checked
                                                    ? "on"
                                                    : [],
                                            )
                                        }
                                    />
                                    <span className="min-w-0">
                                        <span className="block text-sm font-semibold">
                                            I have checked which models took
                                            part.{" "}
                                            <span className="font-normal text-amber-800 dark:text-amber-200">
                                                Required
                                            </span>
                                        </span>
                                        <span
                                            id="participation-help"
                                            className="mt-1 block text-xs text-amber-900 dark:text-amber-100"
                                        >
                                            Include reinforcements that entered
                                            the battle. Leave unused
                                            reinforcements unselected.
                                        </span>
                                    </span>
                                </label>
                            </div>
                            <div className="flex flex-wrap items-center justify-between gap-3">
                                <p className="text-sm text-muted">
                                    Entries save as you go. The gang changes
                                    only when you apply the results.
                                </p>
                                <FormActions className="w-full sm:w-auto">
                                    <Button
                                        busy={form.busyIntent === "save"}
                                        disabled={!!form.pending || form.frozen}
                                        onClick={() => void form.send("save")}
                                    >
                                        Save draft
                                    </Button>
                                    <Button
                                        variant="success"
                                        busy={form.busyIntent === "apply"}
                                        disabled={!!form.pending || form.frozen}
                                        onClick={() => void form.send("apply")}
                                    >
                                        Apply results
                                    </Button>
                                </FormActions>
                            </div>
                        </div>
                    </div>
                </form>
            </WorkflowLayout>
        </div>
    );
}
