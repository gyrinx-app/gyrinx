import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModelPreviewProps } from "../../ui";
import { Preview, type PreviewCache } from "./Preview";

afterEach(() => vi.unstubAllGlobals());

function card(name: string): ModelPreviewProps {
    return {
        name,
        rating: 60,
        profileName: "",
        ownerLine: "",
        typeLine: "Fighter",
        xp: 0,
        xpTarget: "–",
        typeSpan: 1,
        statGroups: [],
        details: [],
        weaponColumns: [],
        weapons: [],
    };
}
function response(name: string) {
    return new Response(JSON.stringify({ preview: card(name) }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
    });
}

describe("Hire preview reads", () => {
    it("requests the selected combination and reuses it when reopened", async () => {
        const fetcher = vi.fn().mockResolvedValue(response("Selected model"));
        vi.stubGlobal("fetch", fetcher);
        const selection = ["second", "first"];
        const cache: PreviewCache = new Map();
        const view = render(
            <Preview
                href="/preview/?entry=offer"
                selection={selection}
                cache={cache}
            />,
        );
        expect(screen.getByRole("status").textContent).toBe("Loading preview…");
        await screen.findByText("Selected model");
        const [url, options] = fetcher.mock.calls[0];
        expect(
            new URL(url, "https://example.test").searchParams.get("selection"),
        ).toBe('["first","second"]');
        expect(
            new URL(url, "https://example.test").searchParams.get("entry"),
        ).toBe("offer");
        expect(options.credentials).toBe("same-origin");
        expect(options.headers.Accept).toBe("application/json");
        expect(selection).toEqual(["second", "first"]);
        view.unmount();
        render(
            <Preview
                href="/preview/?entry=offer"
                selection={selection}
                cache={cache}
            />,
        );
        expect(screen.getByText("Selected model")).toBeTruthy();
        expect(fetcher).toHaveBeenCalledOnce();
    });

    it("ignores an older response after the selected options change", async () => {
        let first!: (response: Response) => void;
        let second!: (response: Response) => void;
        const fetcher = vi
            .fn()
            .mockImplementationOnce(
                () =>
                    new Promise<Response>((resolve) => {
                        first = resolve;
                    }),
            )
            .mockImplementationOnce(
                () =>
                    new Promise<Response>((resolve) => {
                        second = resolve;
                    }),
            );
        vi.stubGlobal("fetch", fetcher);
        const cache: PreviewCache = new Map();
        const view = render(
            <Preview href="/preview/" selection={["first"]} cache={cache} />,
        );
        view.rerender(
            <Preview href="/preview/" selection={["second"]} cache={cache} />,
        );
        expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
        await act(async () => second(response("Current model")));
        expect(screen.getByText("Current model")).toBeTruthy();
        await act(async () => first(response("Old model")));
        expect(screen.queryByText("Old model")).toBeNull();
        expect(screen.getByText("Current model")).toBeTruthy();
        expect(cache.size).toBe(1);
    });

    it("keeps a malformed read local and retains focus while retrying", async () => {
        const user = userEvent.setup();
        const fetcher = vi
            .fn()
            .mockResolvedValueOnce(
                new Response(
                    JSON.stringify({
                        preview: { ...card("Broken"), statGroups: null },
                    }),
                    { headers: { "Content-Type": "application/json" } },
                ),
            )
            .mockResolvedValueOnce(response("Recovered model"));
        vi.stubGlobal("fetch", fetcher);
        render(<Preview href="/preview/" selection={[]} cache={new Map()} />);
        expect((await screen.findByRole("alert")).textContent).toContain(
            "The preview could not be loaded. Try again.",
        );
        expect(screen.queryByText("Broken")).toBeNull();
        await user.click(screen.getByRole("button", { name: "Retry preview" }));
        await screen.findByText("Recovered model");
        expect(document.activeElement).toBe(
            screen.getByRole("region", { name: "Model preview" }),
        );
        expect(fetcher).toHaveBeenCalledTimes(2);
    });

    it.each([
        [401, "Sign in again to load this preview."],
        [404, "This preview is no longer available."],
    ])(
        "explains a %s read without treating it as a model",
        async (status, message) => {
            vi.stubGlobal(
                "fetch",
                vi
                    .fn()
                    .mockResolvedValue(
                        new Response("", { status: Number(status) }),
                    ),
            );
            render(
                <Preview href="/preview/" selection={[]} cache={new Map()} />,
            );
            expect((await screen.findByRole("alert")).textContent).toContain(
                message,
            );
        },
    );
});
