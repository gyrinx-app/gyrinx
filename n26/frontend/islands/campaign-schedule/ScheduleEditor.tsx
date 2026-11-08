import { useState } from "react";
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
    setup: ["template_id", "mode", "current_number"],
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
    plan: ["mode"],
};

export function ScheduleEditor({
    editor,
    phases,
    onNavigate,
    onReload,
}: {
    editor: Editor;
    phases: Phase[];
    onNavigate?: (url: string) => void;
    onReload?: () => void;
}) {
    const [current, setCurrent] = useState(editor.current);
    const [reviewUrl, setReviewUrl] = useState(editor.back);
    const form = useWorkflowForm({
        ...editor,
        onNavigate,
        onReload,
        interpret(status, data) {
            if (status === 200 && typeof data.nextUrl === "string")
                return { kind: "saved", nextUrl: data.nextUrl };
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
    const unavailable = editor.context.unavailable === true;
    const change = (name: string, value: string) =>
        form.setValues({ ...values, [name]: value });
    const fields = new Set(visible[editor.kind] ?? []);
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
                onChange={(event) => change("mode", event.target.value)}
            >
                <option value="fixed">Fixed plan</option>
                <option value="repeating">Repeating pattern</option>
            </NativeSelect>
        </Field>
    );
    const navigate = (url: string) =>
        (onNavigate ?? ((href) => window.location.assign(href)))(url);
    return (
        <Dialog
            title={editor.heading}
            lead={editor.lead}
            formProps={{ method: "post", action: editor.action }}
            pending={form.pending || form.uncertain}
            onSubmit={(event) => {
                if (unavailable && !form.uncertain) event.preventDefault();
                else void form.save(event);
            }}
            onDismiss={() => {
                if (!form.pending && !form.uncertain)
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
            <div className="max-h-[60vh] overflow-y-auto px-1">
                <fieldset
                    disabled={form.frozen || unavailable}
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
                            <Field
                                label="Phase"
                                htmlFor="cycle-phase"
                                errors={errors.phase_id}
                            >
                                <NativeSelect
                                    name="phase_id"
                                    value={values.phase_id}
                                    onChange={(event) =>
                                        change("phase_id", event.target.value)
                                    }
                                >
                                    {phases.map((phase) => (
                                        <option key={phase.id} value={phase.id}>
                                            {phase.name} · {phase.count} saved
                                            cycles
                                        </option>
                                    ))}
                                </NativeSelect>
                            </Field>
                            {text("custom_name", "Custom cycle name", {
                                help: "Leave blank to use its cycle number.",
                            })}
                            <div className="grid gap-3 sm:grid-cols-2">
                                {text("starts_on", "Planned start", {
                                    type: "date",
                                })}
                                {text("ends_on", "Planned end", {
                                    type: "date",
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
                            {mode}
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
                        disabled={form.pending}
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
                    disabled={form.pending || form.uncertain}
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
