import { useState } from "react";
import {
    Button,
    ButtonLink,
    Field,
    FieldErrors,
    Input,
    Textarea,
} from "../../ui";

type FieldData = {
    name: string;
    id: string;
    label: string;
    help: string;
    required: boolean;
    value: string;
    kind: string;
    errors: string[];
    min: number | null;
    max: number | null;
    maxLength: number | null;
};
type FormData = { fields: FieldData[]; errors: string[] };
export type ScenarioAuthoringProps = {
    csrfToken: string;
    table: {
        name: string;
        purpose: string;
        staged: boolean;
        archived: boolean;
        sideJobs: boolean;
    } | null;
    tableForm: FormData;
    addForm: FormData | null;
    entries: {
        id: string;
        roll: number;
        name: string;
        text: string;
        form: FormData;
        image: string;
        imageAlt: string;
    }[];
    errors: string[];
    editing: string;
    complete: boolean;
    previewUrl: string;
};

function Fields({ form }: { form: FormData }) {
    return (
        <div className="space-y-4">
            <FieldErrors errors={form.errors} />
            {form.fields.map((field) => (
                <Field
                    key={field.name}
                    label={field.label}
                    htmlFor={field.id}
                    description={field.help}
                    errors={field.errors}
                >
                    {field.kind === "textarea" ? (
                        <Textarea
                            id={field.id}
                            name={field.name}
                            defaultValue={field.value}
                            required={field.required}
                            rows={5}
                        />
                    ) : (
                        <Input
                            id={field.id}
                            name={field.name}
                            type={field.kind}
                            defaultValue={
                                field.kind === "file" ? undefined : field.value
                            }
                            required={field.required}
                            min={field.min ?? undefined}
                            max={field.max ?? undefined}
                            maxLength={field.maxLength ?? undefined}
                            accept={
                                field.kind === "file"
                                    ? "image/png,image/jpeg,image/webp"
                                    : undefined
                            }
                        />
                    )}
                </Field>
            ))}
        </div>
    );
}

export function ScenarioAuthoring(props: ScenarioAuthoringProps) {
    const [editing, setEditing] = useState(props.editing);
    const csrf = (
        <input
            type="hidden"
            name="csrfmiddlewaretoken"
            value={props.csrfToken}
        />
    );
    const action = (act: string) => (
        <form method="post">
            {csrf}
            <input type="hidden" name="act" value={act} />
            <Button variant="text" size="sm" type="submit">
                {act === "put_live"
                    ? "Put live"
                    : act === "stage"
                      ? "Stage"
                      : act === "retire"
                        ? "Retire set"
                        : "Restore set"}
            </Button>
        </form>
    );
    return (
        <div className="mt-6 max-w-4xl space-y-8">
            <FieldErrors errors={props.errors} />
            {props.table && (
                <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-4">
                        <p className="text-sm text-muted">
                            {props.table.purpose} ·{" "}
                            {props.table.archived
                                ? "Retired"
                                : props.table.staged
                                  ? "Staged"
                                  : "Live"}{" "}
                            · {props.entries.length} of 6 entries
                        </p>
                        {props.previewUrl && (
                            <ButtonLink
                                href={props.previewUrl}
                                variant="ghost"
                                size="sm"
                            >
                                Preview in generator
                            </ButtonLink>
                        )}
                        {props.table.sideJobs && (
                            <>
                                {props.table.archived ? (
                                    action("restore")
                                ) : (
                                    <>
                                        {action(
                                            props.table.staged
                                                ? "put_live"
                                                : "stage",
                                        )}
                                        {action("retire")}
                                    </>
                                )}
                            </>
                        )}
                    </div>
                    {!props.complete && (
                        <p className="text-sm text-muted">
                            Complete all six D6 entries before previewing or
                            putting this table live.
                        </p>
                    )}
                    {!props.table.staged && (
                        <p className="text-sm text-muted">
                            Changes to live wording also appear on saved
                            scenarios.
                        </p>
                    )}
                </div>
            )}
            <section className="space-y-4">
                <h2 className="text-lg font-semibold">
                    {props.table ? "Table details" : "Create a side-job set"}
                </h2>
                <form method="post" className="max-w-xl space-y-4">
                    {csrf}
                    <input type="hidden" name="act" value="edit" />
                    <Fields form={props.tableForm} />
                    <Button variant="success" type="submit">
                        {props.table ? "Save table" : "Create set"}
                    </Button>
                </form>
            </section>
            {props.entries.length > 0 && (
                <section className="space-y-4">
                    <h2 className="text-lg font-semibold">Entries</h2>
                    <ol className="divide-y divide-box-border rounded-box border border-box-border">
                        {props.entries.map((entry) => (
                            <li key={entry.id} className="space-y-3 p-4">
                                <div className="flex items-start justify-between gap-3">
                                    <h3 className="font-semibold">
                                        {entry.roll}. {entry.name}
                                    </h3>
                                    <Button
                                        variant="text"
                                        size="sm"
                                        onClick={() =>
                                            setEditing(
                                                editing === entry.id
                                                    ? ""
                                                    : entry.id,
                                            )
                                        }
                                        aria-expanded={editing === entry.id}
                                    >
                                        {editing === entry.id
                                            ? "Close"
                                            : "Edit entry"}
                                    </Button>
                                </div>
                                {editing === entry.id ? (
                                    <form
                                        method="post"
                                        encType="multipart/form-data"
                                        className="space-y-4"
                                    >
                                        {csrf}
                                        <input
                                            type="hidden"
                                            name="act"
                                            value="edit-entry"
                                        />
                                        <input
                                            type="hidden"
                                            name="entry"
                                            value={entry.id}
                                        />
                                        <Fields form={entry.form} />
                                        <Button variant="success" type="submit">
                                            Save entry
                                        </Button>
                                    </form>
                                ) : (
                                    <p className="max-w-prose whitespace-pre-line">
                                        {entry.text}
                                    </p>
                                )}
                                {entry.image && (
                                    <img
                                        src={entry.image}
                                        alt={entry.imageAlt}
                                        className="w-full max-w-sm rounded border border-box-border"
                                    />
                                )}
                            </li>
                        ))}
                    </ol>
                </section>
            )}
            {props.addForm && (
                <section className="space-y-4">
                    <h2 className="text-lg font-semibold">Add an entry</h2>
                    <form
                        method="post"
                        encType="multipart/form-data"
                        className="max-w-xl space-y-4"
                    >
                        {csrf}
                        <input type="hidden" name="act" value="add-entry" />
                        <Fields form={props.addForm} />
                        <Button variant="success" type="submit">
                            Add entry
                        </Button>
                    </form>
                </section>
            )}
        </div>
    );
}
