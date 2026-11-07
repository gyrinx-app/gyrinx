/** A failed response can leave a write's outcome unknown. Callers retain its payload. */
export class CommandError extends Error {
    constructor(
        message: string,
        public readonly outcome: "rejected" | "unknown",
    ) {
        super(message);
    }
}

export async function postForm(
    url: string,
    body: URLSearchParams,
    csrfToken: string,
): Promise<{ status: number; data: Record<string, unknown> }> {
    let response: Response;
    try {
        response = await fetch(url, {
            method: "POST",
            body,
            credentials: "same-origin",
            redirect: "error",
            headers: { Accept: "application/json", "X-CSRFToken": csrfToken },
        });
    } catch {
        throw new CommandError(
            "The save may have completed. Retry this save to check before making another change.",
            "unknown",
        );
    }
    if (response.status === 401)
        throw new CommandError(
            "Sign in again to save this change.",
            "rejected",
        );
    if (response.status === 403)
        throw new CommandError(
            "Your session could not be verified. Reload the page before saving.",
            "rejected",
        );
    if (response.status === 404)
        throw new CommandError(
            "This page is no longer available to you.",
            "rejected",
        );
    if (response.status >= 500)
        throw new CommandError(
            "The save may have completed. Retry this save to check before making another change.",
            "unknown",
        );
    try {
        if (!response.headers.get("Content-Type")?.includes("application/json"))
            throw new Error();
        const data: unknown = await response.json();
        if (!data || typeof data !== "object" || Array.isArray(data))
            throw new Error();
        return {
            status: response.status,
            data: data as Record<string, unknown>,
        };
    } catch {
        throw new CommandError(
            "The save could not be confirmed. Retry this save before making another change.",
            "unknown",
        );
    }
}

export type FormErrors = Record<string, string[]>;
export function fieldErrors(value: unknown): value is FormErrors {
    return (
        !!value &&
        typeof value === "object" &&
        !Array.isArray(value) &&
        Object.values(value).every(
            (errors) =>
                Array.isArray(errors) &&
                errors.every((error) => typeof error === "string"),
        )
    );
}
