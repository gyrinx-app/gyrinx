import { afterEach, expect, test, vi } from "vitest";
import { postForm } from "./command";
afterEach(() => vi.unstubAllGlobals());
test.each([401, 403, 404])(
    "a %s response confirms rejection",
    async (status) => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status }));
        await expect(
            postForm("/save/", new URLSearchParams(), "csrf"),
        ).rejects.toMatchObject({ outcome: "rejected" });
    },
);
test.each([500, 502, 503])(
    "a %s response leaves the write uncertain",
    async (status) => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status }));
        await expect(
            postForm("/save/", new URLSearchParams(), "csrf"),
        ).rejects.toMatchObject({ outcome: "unknown" });
    },
);
test("HTML and malformed JSON do not confirm a save", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce({
                status: 200,
                headers: new Headers({ "content-type": "text/html" }),
            })
            .mockResolvedValueOnce({
                status: 200,
                headers: new Headers({ "content-type": "application/json" }),
                json: () => {
                    throw new Error();
                },
            }),
    );
    await expect(
        postForm("/save/", new URLSearchParams(), "csrf"),
    ).rejects.toMatchObject({ outcome: "unknown" });
    await expect(
        postForm("/save/", new URLSearchParams(), "csrf"),
    ).rejects.toMatchObject({ outcome: "unknown" });
});
