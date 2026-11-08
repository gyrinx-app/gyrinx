import { useEffect, useRef, useState } from "react";
import { fieldErrors } from "../../http/command";
import {
    Button,
    Dialog,
    Field,
    FieldErrors,
    FormActions,
    Input,
    NativeSelect,
    Textarea,
    useWorkflowForm,
} from "../../ui";
import { PlanSteps } from "./PlanSteps";
import { RewardSettings } from "./RewardSettings";
import type { Editor, Phase } from "./types";

const visible: Record<string, string[]> = {
    setup: [
        "template_id",
        "mode",
        "current_number",
        "date_start",
        "cycle_interval",
        "cycle_unit",
    ],
    template: ["template_id", "mode"],
    cycle: [
        "phase_id",
        "custom_name",
        "starts_on",
        "ends_on",
        "description",
        "effects",
    ],
    phase: ["name", "description", "effects"],
    "duplicate-phase": ["name"],
    "save-template": ["name"],
    plan: ["mode", "date_start", "cycle_interval", "cycle_unit"],
};

export function ScheduleEditor({
    editor,
    phases,
    onNavigate,
    onReload,
    navigation,
}: {
    editor: Editor;
    phases: Phase[];
    onNavigate?: (url: string) => void;
    onReload?: () => void;
    navigation?: {
        pending: boolean;
        error: string;
        retry: () => void;
        setGuard: (value: boolean) => void;
    };
}) {
    const [confirmed, setConfirmed] = useState(false);
    const [current, setCurrent] = useState(editor.current);
    const [reviewUrl, setReviewUrl] = useState(editor.back);
    const form = useWorkflowForm({
        ...editor,
        optionalRecoveryFields: ["date_start", "cycle_interval", "cycle_unit", "date_version"],
        onNavigate,
        onReload,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string") {
                if (navigation) setConfirmed(true);
                return { kind: "saved", nextUrl: data.nextUrl };
            }
            if (
                status === 409 &&
                data.code === "revision_conflict" &&
                fieldErrors(data.errors) &&
                data.current &&
                typeof data.current === "object" &&
                "cycle" in data.current &&
                typeof data.current.cycle === "string"
            ) {
                setCurrent(data.current as Editor["current"]);
                if (typeof data.reviewUrl === "string")
                    setReviewUrl(data.reviewUrl);
                return { kind: "conflict", errors: data.errors };
            }
            if (
                (status === 422 ||
                    (status === 409 && data.code === "request_key_conflict")) &&
                fieldErrors(data.errors)
            )
                return { kind: "invalid", errors: data.errors };
            return null;
        },
    });
    const { values, errors } = form;
    const modeDrafts = useRef<Record<string, string>>({
        [values.mode]: values.steps,
    });
    const setGuard = navigation?.setGuard;
    useEffect(() => {
        setGuard?.(form.pending || form.uncertain || confirmed);
        return () => setGuard?.(false);
    }, [form.pending, form.uncertain, confirmed, setGuard]);
    const unavailable = editor.context.unavailable === true;
    const change = (name: string, value: string) =>
        form.setValues({ ...values, [name]: value });
    const datesOnly =
        editor.kind === "cycle" && editor.context.datesOnly === true;
    const fields = new Set(
        datesOnly ? ["starts_on", "ends_on"] : (visible[editor.kind] ?? []),
    );
    const text = (
        name: string,
        label: string,
        options: {
            type?: string;
            required?: boolean;
            min?: string;
            max?: string;
            help?: string;
        } = {},
    ) => (
        <Field
            label={label}
            htmlFor={`cycle-${name}`}
            errors={errors[name]}
            description={options.help}
        >
            <Input
                name={name}
                value={values[name] ?? ""}
                type={options.type ?? "text"}
                required={options.required}
                min={options.min}
                max={options.max}
                onChange={(event) => change(name, event.target.value)}
            />
        </Field>
    );
    const mode = (
        <Field label="Planning mode" htmlFor="cycle-mode" errors={errors.mode}>
            <NativeSelect
                name="mode"
                value={values.mode}
                onChange={(event) => {
                    const mode = event.target.value;
                    if (editor.kind !== "plan") return change("mode", mode);
                    modeDrafts.current[values.mode] = values.steps;
                    const proposed =
                        mode === "repeating"
                            ? editor.context.patternSteps
                            : editor.context.fixedSteps;
                    const steps =
                        modeDrafts.current[mode] ??
                        (Array.isArray(proposed)
                            ? JSON.stringify(proposed)
                            : values.steps);
                    form.setValues({ ...values, mode, steps });
                }}
            >
                <option value="fixed">Fixed plan</option>
                <option value="repeating">Repeating pattern</option>
            </NativeSelect>
        </Field>
    );
    const dates = "date_start" in editor.values && (
        <section className="space-y-3" aria-label="Cycle dates">
            <h3 className="font-semibold">Cycle dates</h3>
            {text(
                "date_start",
                editor.kind === "setup" || editor.context.needsDates
                    ? "Cycle 1 starts"
                    : "First projected cycle starts",
                { type: "date", required: values.date_version === "1" },
            )}
            <div className="grid grid-cols-2 gap-3">
                {text("cycle_interval", "Cycle length", {
                    type: "number",
                    min: "1",
                    max: "520",
                    required: values.date_version === "1",
                })}
                <Field
                    label="Unit"
                    htmlFor="cycle-cycle_unit"
                    errors={errors.cycle_unit}
                >
                    <NativeSelect
                        name="cycle_unit"
                        value={values.cycle_unit}
                        onChange={(event) =>
                            change("cycle_unit", event.target.value)
                        }
                    >
                        <option value="weeks">Weeks</option>
                        <option value="months">Calendar months</option>
                    </NativeSelect>
                </Field>
            </div>
            <p className="text-sm text-muted">
                Each range includes its start and end dates. Saved cycle dates
                stay unchanged when future timing changes.
            </p>
            {editor.context.needsDates === true && (
                <p className="text-sm">
                    These settings fill missing dates on saved cycles. Existing
                    date ranges are retained.
                </p>
            )}
        </section>
    );
    const navigate = (url: string) =>
        (onNavigate ?? ((href) => window.location.assign(href)))(url);
    return (
        <Dialog
            title={editor.heading}
            lead={editor.lead}
            formProps={{ method: "post", action: editor.action }}
            pending={
                form.pending ||
                form.uncertain ||
                confirmed ||
                navigation?.pending
            }
            onSubmit={(event) => {
                if (unavailable && !form.uncertain) event.preventDefault();
                else void form.save(event);
            }}
            onDismiss={() => {
                if (
                    !form.pending &&
                    !form.uncertain &&
                    !confirmed &&
                    !navigation?.pending
                )
                    form.conflicted
                        ? form.review(editor.back)
                        : navigate(editor.back);
            }}
        >
            <input
                type="hidden"
                name="csrfmiddlewaretoken"
                value={editor.csrfToken}
            />
            {Object.entries(values)
                .filter(([name]) => !fields.has(name))
                .map(([name, value]) => (
                    <input key={name} type="hidden" name={name} value={value} />
                ))}
            {form.hasErrors && (
                <div
                    ref={form.summary}
                    tabIndex={-1}
                    role="alert"
                    aria-label="Schedule save errors"
                >
                    <FieldErrors
                        errors={[
                            ...Object.values(errors).flat(),
                            ...(form.notice ? [form.notice] : []),
                        ]}
                    />
                </div>
            )}
            {form.conflicted && current && (
                <div className="rounded-control border border-box-border p-3 text-sm">
                    <p className="font-medium">Current schedule</p>
                    <p>
                        {current.cycle}
                        {current.phase ? ` · ${current.phase}` : ""}
                    </p>
                    <p className="mt-2">
                        Your draft remains below. Review the current schedule
                        before making another change.
                    </p>
                </div>
            )}
            {navigation?.pending && (
                <p role="status" className="text-sm text-muted">
                    {confirmed
                        ? "Saved. Updating schedule…"
                        : "Loading schedule…"}
                </p>
            )}
            {navigation?.error && (
                <div role="alert" className="text-sm">
                    <p>{navigation.error}</p>
                    <Button size="sm" onClick={navigation.retry}>
                        Try again
                    </Button>
                </div>
            )}
            <div className="max-h-[60vh] overflow-y-auto px-1">
                <fieldset
                    disabled={
                        form.frozen ||
                        unavailable ||
                        confirmed ||
                        navigation?.pending
                    }
                    className="space-y-4"
                >
                    {(editor.kind === "setup" ||
                        editor.kind === "template") && (
                        <>
                            <Field
                                label="Schedule template"
                                htmlFor="cycle-template"
                                errors={errors.template_id}
                            >
                                <NativeSelect
                                    name="template_id"
                                    required
                                    value={values.template_id}
                                    onChange={(event) =>
                                        change(
                                            "template_id",
                                            event.target.value,
                                        )
                                    }
                                >
                                    <option value="">Choose a template</option>
                                    {editor.templates.map((template) => (
                                        <option
                                            key={template.id}
                                            value={template.id}
                                        >
                                            {template.name}
                                        </option>
                                    ))}
                                </NativeSelect>
                            </Field>
                            {mode}
                            {editor.kind === "setup" &&
                                text("current_number", "Current cycle number", {
                                    type: "number",
                                    required: true,
                                    min: "1",
                                    max: "1000",
                                })}
                            {editor.kind === "setup" && dates}
                            {editor.context.activates === true && (
                                <p className="text-sm">
                                    Setting up cycles starts the chosen cycle
                                    and notifies accepted players.
                                </p>
                            )}
                        </>
                    )}
                    {fields.has("name") &&
                        text(
                            "name",
                            editor.kind === "save-template"
                                ? "Template name"
                                : "Phase name",
                            { required: true },
                        )}
                    {editor.kind === "cycle" && (
                        <>
                            {!datesOnly && (
                                <>
                                    <Field
                                        label="Phase"
                                        htmlFor="cycle-phase"
                                        errors={errors.phase_id}
                                    >
                                        <NativeSelect
                                            name="phase_id"
                                            value={values.phase_id}
                                            onChange={(event) =>
                                                change(
                                                    "phase_id",
                                                    event.target.value,
                                                )
                                            }
                                        >
                                            {phases.map((phase) => (
                                                <option
                                                    key={phase.id}
                                                    value={phase.id}
                                                >
                                                    {phase.name} · {phase.count}{" "}
                                                    saved cycles
                                                </option>
                                            ))}
                                        </NativeSelect>
                                    </Field>
                                    {text("custom_name", "Custom cycle name", {
                                        help: "Leave blank to use its cycle number.",
                                    })}
                                </>
                            )}
                            <div className="grid gap-3 sm:grid-cols-2">
                                {text("starts_on", "Start date", {
                                    type: "date",
                                    required: values.date_version === "1",
                                })}
                                {text("ends_on", "End date", {
                                    type: "date",
                                    required: values.date_version === "1",
                                })}
                            </div>
                        </>
                    )}
                    {fields.has("description") && (
                        <Field
                            label="Description and rules"
                            htmlFor="cycle-description"
                            errors={errors.description}
                        >
                            <Textarea
                                name="description"
                                rows={4}
                                value={values.description}
                                onChange={(event) =>
                                    change("description", event.target.value)
                                }
                            />
                        </Field>
                    )}
                    {fields.has("effects") && (
                        <Field
                            label="Effects"
                            htmlFor="cycle-effects"
                            errors={errors.effects}
                        >
                            <Textarea
                                name="effects"
                                rows={3}
                                value={values.effects}
                                onChange={(event) =>
                                    change("effects", event.target.value)
                                }
                            />
                        </Field>
                    )}
                    {editor.kind === "phase" && (
                        <RewardSettings
                            value={values.rewards}
                            onChange={(value) => change("rewards", value)}
                        />
                    )}
                    {editor.kind === "plan" && (
                        <>
                            {dates}
                            {mode}
                            {values.mode !== editor.values.mode && (
                                <p className="text-sm text-muted">
                                    Review the phase counts below before
                                    switching modes. Saved cycles and their
                                    dates are retained.
                                </p>
                            )}
                            <PlanSteps
                                value={values.steps}
                                phases={phases}
                                disabled={form.frozen}
                                onChange={(value) => change("steps", value)}
                            />
                        </>
                    )}
                    {editor.context.savesNext === true && (
                        <p className="text-sm">
                            The next projected cycle will be saved and activated
                            together.
                        </p>
                    )}
                </fieldset>
            </div>
            <FormActions>
                {form.conflicted || (unavailable && !form.uncertain) ? (
                    <Button
                        variant="primary"
                        onClick={() =>
                            form.conflicted
                                ? form.review(reviewUrl)
                                : navigate(editor.back)
                        }
                    >
                        Review current schedule
                    </Button>
                ) : (
                    <Button
                        type="submit"
                        variant="success"
                        disabled={
                            form.pending || confirmed || navigation?.pending
                        }
                    >
                        {form.pending
                            ? "Saving…"
                            : form.uncertain
                              ? "Retry save"
                              : [
                                      "advance",
                                      "start",
                                      "finish",
                                      "delete-phase",
                                  ].includes(editor.kind)
                                ? editor.heading
                                : "Save"}
                    </Button>
                )}
                <Button
                    variant="ghost"
                    disabled={
                        form.pending ||
                        form.uncertain ||
                        confirmed ||
                        navigation?.pending
                    }
                    onClick={() =>
                        form.conflicted
                            ? form.review(editor.back)
                            : navigate(editor.back)
                    }
                >
                    Cancel
                </Button>
            </FormActions>
        </Dialog>
    );
}
