import { afterEach, describe, expect, it, vi } from "vitest";
import {
    mountWithin,
    pageInsertions,
    watchInsertions,
} from "../../core/static/n26/react-islands.js";

// The page observer would import every host these tests append.
pageInsertions?.disconnect();

function cleanup(element = document.body) {
    document.dispatchEvent(
        new CustomEvent("htmx:beforeCleanupElement", {
            detail: { elt: element },
        }),
    );
}

function host(id = "one") {
    const element = document.createElement("div");
    element.dataset.reactModule = "/module.js";
    element.dataset.reactProps = `props-${id}`;
    element.dataset.reactError = `error-${id}`;
    const props = document.createElement("script");
    props.type = "application/json";
    props.id = element.dataset.reactProps;
    props.textContent = JSON.stringify({ label: id });
    const error = document.createElement("template");
    error.id = element.dataset.reactError;
    error.innerHTML =
        '<div role="alert"><p data-react-error-message></p><button data-react-retry type="button"><span data-react-retry-spinner hidden></span>Try again</button><a data-react-reload>Reload page</a></div>';
    document.body.append(element, props, error);
    return element;
}

afterEach(() => {
    cleanup();
    document.body.replaceChildren();
    vi.restoreAllMocks();
});

describe("island lifecycle", () => {
    it("mounts independent roots once, passes props and disposes each before a swap", async () => {
        const first = host("first");
        const second = host("second");
        const dispose = vi.fn();
        const mount = vi.fn(() => dispose);
        const load = vi.fn().mockResolvedValue({ mount });
        mountWithin(document, load);
        mountWithin(document, load);
        await vi.waitFor(() => expect(mount).toHaveBeenCalledTimes(2));
        expect(load).toHaveBeenCalledTimes(2);
        expect(mount).toHaveBeenCalledWith(first, { label: "first" });
        expect(mount).toHaveBeenCalledWith(second, { label: "second" });
        cleanup(first);
        expect(dispose).toHaveBeenCalledTimes(1);
        cleanup();
        expect(dispose).toHaveBeenCalledTimes(2);
    });

    it("does not mount a cancelled import even if its host remains connected", async () => {
        const element = host();
        let resolve;
        const mount = vi.fn();
        mountWithin(
            element,
            () =>
                new Promise((done) => {
                    resolve = done;
                }),
        );
        cleanup(element);
        resolve({ mount });
        await Promise.resolve();
        expect(mount).not.toHaveBeenCalled();
    });

    it("explains a failed connection and offers retry without navigation", async () => {
        const element = host();
        vi.spyOn(console, "error").mockImplementation(() => {});
        mountWithin(element, () => Promise.reject(new Error("chunk removed")));
        await vi.waitFor(() =>
            expect(element.querySelector('[role="alert"]')).not.toBeNull(),
        );
        expect(element.querySelector("a").href).toBe(window.location.href);
        expect(
            element.querySelector("[data-react-error-message]").textContent,
        ).toBe(
            "Gyrinx could not load this section. Check your connection and try again.",
        );
        expect(element.querySelector("button").textContent).toBe("Try again");
    });

    it("retries a failed import at a fresh URL and leaves other sections alone", async () => {
        const element = host();
        const other = host("other");
        other.innerHTML = '<input value="Unsaved draft">';
        vi.spyOn(console, "error").mockImplementation(() => {});
        let resolve;
        const mount = vi.fn((target) => {
            target.textContent = "Recovered";
        });
        const load = vi
            .fn()
            .mockRejectedValueOnce(
                new TypeError("Failed to fetch dynamically imported module"),
            )
            .mockImplementationOnce(
                () =>
                    new Promise((done) => {
                        resolve = done;
                    }),
            );
        mountWithin(element, load);
        await vi.waitFor(() =>
            expect(element.querySelector("button")).not.toBeNull(),
        );
        const retry = element.querySelector("button");
        retry.click();
        retry.click();
        expect(retry.disabled).toBe(true);
        expect(retry.getAttribute("aria-busy")).toBe("true");
        expect(element.querySelector("[data-react-retry-spinner]").hidden).toBe(
            false,
        );
        expect(load).toHaveBeenCalledTimes(2);
        const url = new URL(load.mock.calls[1][0]);
        expect(url.pathname).toBe("/module.js");
        expect(url.searchParams.get("retry")).toBe("1");
        resolve({ mount });
        await vi.waitFor(() => expect(element.textContent).toBe("Recovered"));
        expect(other.querySelector("input").value).toBe("Unsaved draft");
    });

    it("describes a mounting exception separately from a failed connection", async () => {
        const element = host();
        vi.spyOn(console, "error").mockImplementation(() => {});
        mountWithin(element, () =>
            Promise.resolve({
                mount: () => {
                    throw new Error("Invalid props");
                },
            }),
        );
        await vi.waitFor(() =>
            expect(element.textContent).toContain(
                "This section stopped working.",
            ),
        );
        expect(element.textContent).not.toContain("Check your connection");
    });

    it("leaves a server-drawn control standing when its import fails", async () => {
        const element = host();
        element.setAttribute("data-react-fallback", "");
        const drawn = document.createElement("a");
        drawn.href = "/gangs/";
        element.append(drawn);
        const logged = vi.spyOn(console, "error").mockImplementation(() => {});
        mountWithin(element, () => Promise.reject(new Error("chunk removed")));
        await vi.waitFor(() => expect(logged).toHaveBeenCalled());
        expect(element.querySelector('[role="alert"]')).toBeNull();
        expect(element.contains(drawn)).toBe(true);
    });

    it("mounts a host delivered by htmx and unmounts it before removal", async () => {
        const element = host();
        element.dataset.reactModule =
            "data:text/javascript,export function mount(host, props) { host.textContent = props.label; return () => host.replaceChildren(); }";
        document.dispatchEvent(
            new CustomEvent("htmx:load", { detail: { elt: element } }),
        );
        await vi.waitFor(() => expect(element.textContent).toBe("one"));
        cleanup(element);
        expect(element.textContent).toBe("");
    });

    it("mounts a host inserted after the first paint and drops it when that node leaves", async () => {
        const scope = document.createElement("div");
        document.body.append(scope);
        const observer = watchInsertions(scope);
        try {
            const wrap = document.createElement("div");
            const element = document.createElement("div");
            element.dataset.reactModule =
                "data:text/javascript,export function mount(host, props) { host.textContent = props.label; return () => host.replaceChildren(); }";
            element.dataset.reactProps = "props-late";
            const props = document.createElement("script");
            props.id = "props-late";
            props.type = "application/json";
            props.textContent = JSON.stringify({ label: "late" });
            document.body.append(props);
            wrap.append(element);
            scope.append(wrap);
            await vi.waitFor(() => expect(element.textContent).toBe("late"));
            wrap.remove();
            await vi.waitFor(() => expect(element.textContent).toBe(""));
        } finally {
            observer.disconnect();
        }
    });
});
