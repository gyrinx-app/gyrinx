import { beforeAll, describe, expect, it, vi } from "vitest";

class Transfer {
    files = [];
    strings = new Map();
    items = { add: (file) => this.files.push(file) };
    get types() {
        return [
            ...this.strings.keys(),
            ...(this.files.length ? ["Files"] : []),
        ];
    }
    setData(type, value) {
        this.strings.set(type, value);
    }
    getData(type) {
        return this.strings.get(type) || "";
    }
}

beforeAll(async () => {
    await import("../../core/static/n26/richtext.js");
});

function intercept(event) {
    const on = vi.fn();
    window.n26CampaignImages({ on });
    expect(on).toHaveBeenCalledWith("paste drop", expect.any(Function), true);
    vi.stubGlobal("DataTransfer", Transfer);
    on.mock.calls[0][1](event);
    vi.unstubAllGlobals();
}

describe("campaign summary image transfers", () => {
    it.each(["paste", "drop"])(
        "recognises a PNG with missing MIME metadata on %s and preserves accompanying text",
        (type) => {
            const data = new Transfer();
            data.items.add(
                new File(["PNG bytes"], "Screenshot.PNG", {
                    lastModified: 123,
                }),
            );
            data.setData("text/html", "<p>Campaign map</p>");
            data.setData("text/plain", "Campaign map");
            const property =
                type === "paste" ? "clipboardData" : "dataTransfer";
            const event = { type, [property]: data };
            intercept(event);
            const transferred = event[property];
            expect(transferred.files[0].type).toBe("image/png");
            expect(transferred.files[0].name).toBe("Screenshot.PNG");
            expect(transferred.files[0].lastModified).toBe(123);
            expect(transferred.getData("text/html")).toBe(
                "<p>Campaign map</p>",
            );
            expect(transferred.getData("text/plain")).toBe("Campaign map");
        },
    );

    it("leaves known MIME types and unsupported files to TinyMCE", () => {
        const data = new Transfer();
        data.items.add(
            new File(["image"], "photo.png", { type: "image/jpeg" }),
        );
        data.items.add(new File(["document"], "campaign.pdf"));
        const event = { type: "drop", dataTransfer: data };
        intercept(event);
        expect(event.dataTransfer).toBe(data);
        expect(data.files[0].type).toBe("image/jpeg");
        expect(data.files[1].type).toBe("");
    });
});
