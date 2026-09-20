import { afterEach, describe, expect, it, vi } from "vitest";
import { mountWithin } from "../core/static/n26/react-islands.js";

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
    const props = document.createElement("script");
    props.type = "application/json";
    props.id = element.dataset.reactProps;
    props.textContent = JSON.stringify({ label: id });
    document.body.append(element, props);
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

    it("reports a failed import with a recovery link", async () => {
        const element = host();
        vi.spyOn(console, "error").mockImplementation(() => {});
        mountWithin(element, () => Promise.reject(new Error("chunk removed")));
        await vi.waitFor(() =>
            expect(element.querySelector('[role="alert"]')).not.toBeNull(),
        );
        expect(element.querySelector("a").href).toBe(window.location.href);
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
});
