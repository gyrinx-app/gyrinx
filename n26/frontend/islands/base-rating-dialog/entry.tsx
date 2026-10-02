import { mount as mountRoot } from "../../runtime/mount";
import {
    BaseRatingDialog,
    type BaseRatingDialogProps,
} from "./BaseRatingDialog";

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

export async function saveBaseRatingDialog(
    source: HTMLElement | null,
    props: BaseRatingDialogProps,
    value: string,
    removing: boolean,
) {
    const htmx = (window as Window & { htmx?: Htmx }).htmx;
    if (!htmx || !source) throw new Error("Unavailable");
    let answered = false;
    const received = (event: Event) => {
        answered =
            (
                event as CustomEvent<{ xhr: XMLHttpRequest }>
            ).detail.xhr.getResponseHeader("HX-Replace-Url") !== null;
    };
    // Read the response before OOB replacement removes the outer Django host.
    source.addEventListener("htmx:beforeOnLoad", received);
    try {
        await htmx.ajax("POST", props.actionUrl, {
            source,
            swap: "none",
            values: {
                rating: value,
                ...(removing ? { act: "remove-override" } : {}),
                csrfmiddlewaretoken: props.csrfToken,
            },
        });
        // Login and CSRF redirects may become 200 responses to XHR.
        if (!answered) throw new Error("Unexpected response");
    } finally {
        source.removeEventListener("htmx:beforeOnLoad", received);
    }
}

export function mount(element: HTMLElement, props: BaseRatingDialogProps) {
    const source = element.closest<HTMLElement>("#n26-rating-dialog-host");
    return mountRoot(element, BaseRatingDialog, {
        ...props,
        onSave: (value: string, removing: boolean) =>
            saveBaseRatingDialog(source, props, value, removing),
    });
}
