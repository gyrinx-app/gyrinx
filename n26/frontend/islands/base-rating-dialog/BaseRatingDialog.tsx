import { useId, useRef, useState } from "react";
import {
    Button,
    Dialog,
    Field,
    FormActions,
    Input,
    Link,
    RatingBaseline,
} from "../../ui";

export type BaseRatingDialogProps = {
    value: string;
    errors: string[];
    formErrors: string[];
    description: string;
    actionUrl: string;
    cancelUrl: string;
    csrfToken: string;
    returnFocusId?: string;
    defaultRating: number;
    hasOverride: boolean;
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

export function BaseRatingDialog(props: BaseRatingDialogProps) {
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
    async function save(removing = false) {
        if (submitting.current) return;
        submitting.current = true;
        setPending(true);
        setError("");
        try {
            const htmx = (window as Window & { htmx?: Htmx }).htmx;
            const source = document.getElementById("n26-rating-dialog-host");
            if (!htmx || !source) throw new Error("Unavailable");
            let answered = false;
            const received = (event: Event) => {
                const detail = (event as CustomEvent<{ xhr: XMLHttpRequest }>)
                    .detail;
                answered =
                    detail.xhr.getResponseHeader("HX-Replace-Url") !== null;
            };
            source.addEventListener("htmx:afterRequest", received);
            // htmx owns the outer hosts, never React's dialog children.
            try {
                await htmx.ajax("POST", props.actionUrl, {
                    source,
                    swap: "none",
                    values: {
                        rating: value,
                        csrfmiddlewaretoken: props.csrfToken,
                        ...(removing ? { act: "remove-override" } : {}),
                    },
                });
                // Login and CSRF redirects may become 200 responses to XHR.
                if (!answered) throw new Error("Unexpected response");
            } finally {
                source.removeEventListener("htmx:afterRequest", received);
            }
        } catch {
            setError("The rating could not be saved. Try again.");
        } finally {
            submitting.current = false;
            setPending(false);
        }
    }
    if (closed) return null;
    return (
        <Dialog
            title="Override base rating"
            pending={pending}
            returnFocusId={props.returnFocusId}
            onDismiss={dismiss}
            onSubmit={(event) => {
                event.preventDefault();
                void save();
            }}
        >
            {[...props.formErrors, error]
                .filter(Boolean)
                .map((message, index) => (
                    <p key={index} role="alert">
                        {message}
                    </p>
                ))}
            {error && <Link href={props.cancelUrl}>Reload the page</Link>}
            <RatingBaseline rating={props.defaultRating} />
            <Field
                label="Base rating (¢)"
                htmlFor={id}
                errors={props.errors}
                description={props.description}
            >
                <Input
                    id={id}
                    name="rating"
                    type="number"
                    required
                    autoFocus
                    min={-2147483648}
                    max={2147483647}
                    step={1}
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                    disabled={pending}
                />
            </Field>
            <FormActions>
                <Button onClick={dismiss} disabled={pending}>
                    Cancel
                </Button>
                <Button
                    disabled={pending || !props.hasOverride}
                    onClick={() => {
                        void save(true);
                    }}
                >
                    Remove Override
                </Button>
                <Button type="submit" variant="success" disabled={pending}>
                    {pending ? "Saving…" : "Save"}
                </Button>
            </FormActions>
        </Dialog>
    );
}
