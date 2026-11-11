import { act, fireEvent, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { mount } from "./mount";

afterEach(() => vi.restoreAllMocks());

it("retries a crashed section without reloading other roots or their drafts", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const host = document.createElement("div");
    host.dataset.reactError = "runtime-error";
    const template = document.createElement("template");
    template.id = host.dataset.reactError;
    template.innerHTML =
        '<div role="alert"><p data-react-error-message></p><button data-react-retry type="button">Try again</button><a data-react-reload>Reload page</a></div>';
    const other = document.createElement("input");
    other.value = "Unsaved draft";
    document.body.append(host, template, other);
    let broken = true;
    function View() {
        if (broken) throw new Error("Render failed");
        return <p>Recovered section</p>;
    }
    let dispose = () => {};
    try {
        act(() => {
            dispose = mount(host, View, {});
        });
        expect(within(host).getByRole("alert").textContent).toContain(
            "This section stopped working.",
        );
        expect(
            within(host)
                .getByRole("link", { name: "Reload page" })
                .getAttribute("href"),
        ).toBe(window.location.href);
        broken = false;
        fireEvent.click(
            within(host).getByRole("button", { name: "Try again" }),
        );
        expect(host.textContent).toBe("Recovered section");
        expect(other.value).toBe("Unsaved draft");
    } finally {
        act(() => dispose());
        host.remove();
        template.remove();
        other.remove();
    }
});
