import { useId, useRef, useState } from "react";
import { Button, Dialog, Field, FormActions, Input, Link } from "../../ui";

export type RenameDialogProps = {
    name: string;
    value: string;
    errors: string[];
    actionUrl: string;
    cancelUrl: string;
    csrfToken: string;
    returnFocusId: string;
};
type Htmx = {
    ajax: (
        method: string,
        url: string,
        options: {
            source: HTMLElement;
            swap: string;
            values: Record<string, string>;
        },
    ) => Promise<unknown>;
};
export function RenameDialog(props: RenameDialogProps) {
    const id = useId();
    const [value, setValue] = useState(props.value);
    const [pending, setPending] = useState(false);
    const submitting = useRef(false);
    const [closed, setClosed] = useState(false);
    const [error, setError] = useState("");
    function dismiss() {
        history.replaceState(history.state, "", props.cancelUrl);
        setClosed(true);
    }
    if (closed) return null;
    return (
        <Dialog
            title="Edit name"
            lead={props.name}
            pending={pending}
            returnFocusId={props.returnFocusId}
            onDismiss={dismiss}
            onSubmit={async (event) => {
                event.preventDefault();
                if (submitting.current) return;
                submitting.current = true;
                setPending(true);
                setError("");
                try {
                    const htmx = (window as Window & { htmx?: Htmx }).htmx;
                    const source = document.getElementById(
                        "n26-rename-dialog-host",
                    );
                    if (!htmx || !source) throw new Error("Unavailable");
                    let answered = false;
                    const received = (event: Event) => {
                        answered =
                            (
                                event as CustomEvent<{ xhr: XMLHttpRequest }>
                            ).detail.xhr.getResponseHeader("HX-Replace-Url") !==
                            null;
                    };
                    source.addEventListener("htmx:afterRequest", received);
                    try {
                        await htmx.ajax("POST", props.actionUrl, {
                            source,
                            swap: "none",
                            values: {
                                name: value,
                                csrfmiddlewaretoken: props.csrfToken,
                            },
                        });
                        if (!answered) throw new Error("Unexpected response");
                    } finally {
                        source.removeEventListener(
                            "htmx:afterRequest",
                            received,
                        );
                    }
                } catch {
                    setError("The name could not be saved. Try again.");
                } finally {
                    submitting.current = false;
                    setPending(false);
                }
            }}
        >
            {error && (
                <>
                    <p role="alert">{error}</p>
                    <Link href={props.cancelUrl}>Reload the page</Link>
                </>
            )}
            <Field label="Name" htmlFor={id} errors={props.errors}>
                <Input
                    id={id}
                    name="name"
                    required
                    maxLength={200}
                    autoComplete="off"
                    autoFocus
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                    disabled={pending}
                />
            </Field>
            <FormActions>
                <Button onClick={dismiss} disabled={pending}>
                    Cancel
                </Button>
                <Button type="submit" variant="success" disabled={pending}>
                    {pending ? "Saving…" : "Save"}
                </Button>
            </FormActions>
        </Dialog>
    );
}
