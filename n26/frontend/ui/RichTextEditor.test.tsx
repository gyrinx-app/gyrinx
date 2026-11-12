import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { RichTextEditor } from "./RichTextEditor";

afterEach(() => {
    vi.unstubAllGlobals();
    delete (window as any).tinymce;
});

test("the campaign editor keeps its draft, uploads with fresh CSRF, and cleans up", async () => {
    const callbacks: Record<string, () => void> = {};
    let value = "";
    const instance = {
        on: (event: string, callback: () => void) => {
            callbacks[event] = callback;
        },
        setContent: vi.fn((next: string) => {
            value = next;
        }),
        getContent: () => value,
        mode: { set: vi.fn() },
        remove: vi.fn(),
    };
    let settings: Record<string, any> = {};
    const init = vi.fn(async (config) => {
        settings = config;
        config.setup(instance);
        callbacks.init();
        return [instance];
    });
    (window as any).tinymce = { init };
    const change = vi.fn();
    const uploading = vi.fn();
    const config = {
        scriptUrl: "/editor-test.js",
        imageSetupUrl: "/images-test.js",
        uploadUrl: "/tinymce/upload/",
        config: { toolbar: "bold image" },
    };
    const view = render(
        <RichTextEditor
            id="message"
            label="Message"
            value="<p>Draft</p>"
            onChange={change}
            config={config}
            csrfToken="old"
            onUploading={uploading}
        />,
    );
    await waitFor(() =>
        expect(
            document.querySelector('script[src="/images-test.js"]'),
        ).toBeTruthy(),
    );
    fireEvent.load(document.querySelector('script[src="/images-test.js"]')!);
    await waitFor(() =>
        expect(
            document.querySelector('script[src="/editor-test.js"]'),
        ).toBeTruthy(),
    );
    fireEvent.load(document.querySelector('script[src="/editor-test.js"]')!);
    await waitFor(() => expect(init).toHaveBeenCalledTimes(1));
    expect(value).toBe("<p>Draft</p>");
    value = "<p><strong>Changed</strong></p>";
    callbacks["input change undo redo"]();
    expect(change).toHaveBeenLastCalledWith(value);
    view.rerender(
        <RichTextEditor
            id="message"
            label="Message"
            value={value}
            onChange={change}
            config={config}
            csrfToken="fresh"
            onUploading={uploading}
            disabled
        />,
    );
    expect(instance.mode.set).toHaveBeenLastCalledWith("readonly");
    const fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ location: "/media/map.png" }),
    });
    vi.stubGlobal("fetch", fetch);
    const image = new Blob(["test"], { type: "image/png" });
    expect(
        await settings.images_upload_handler({
            blob: () => image,
            filename: () => "map.png",
        }),
    ).toBe("/media/map.png");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("fresh");
    expect(uploading.mock.calls.map((args) => args[0])).toEqual([true, false]);
    view.unmount();
    expect(instance.remove).toHaveBeenCalledTimes(1);
});

test("an unavailable editor leaves an editable text field and an explanation", async () => {
    const change = vi.fn();
    render(
        <RichTextEditor
            id="unavailable"
            label="Message"
            value="Draft"
            onChange={change}
            csrfToken="token"
            config={{
                scriptUrl: "/unavailable-editor.js",
                imageSetupUrl: "/unavailable-images.js",
                uploadUrl: "/tinymce/upload/",
                config: {},
            }}
        />,
    );
    await waitFor(() =>
        expect(
            document.querySelector('script[src="/unavailable-images.js"]'),
        ).toBeTruthy(),
    );
    fireEvent.error(
        document.querySelector('script[src="/unavailable-images.js"]')!,
    );
    await screen.findByText(/The editor could not load/);
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), {
        target: { value: "Retained draft" },
    });
    expect(change).toHaveBeenLastCalledWith("Retained draft");
});
