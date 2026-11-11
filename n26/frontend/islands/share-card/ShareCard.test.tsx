import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
    customRatio,
    embedCode,
    embedDimensionStyle,
    ShareCard,
    shareCardTools,
    type Stage,
} from "./ShareCard";

const props = {
    name: "Mother Vex",
    gang: "Venom Sisters",
    cardUrl: "/n26/fighters/1/card/",
};
const address =
    new URL(props.cardUrl, window.location.href).href + "?theme=light";
const png = new Blob(["png"], { type: "image/png" });
let removed: ReturnType<typeof vi.fn<() => void>>;
beforeEach(() => {
    document.documentElement.classList.remove("dark");
    HTMLDialogElement.prototype.showModal = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.setAttribute("open", "");
    });
    HTMLDialogElement.prototype.close = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.removeAttribute("open");
    });
    removed = vi.fn();
    vi.spyOn(shareCardTools, "stage").mockResolvedValue({
        card: document.createElement("div"),
        remove: removed,
    } satisfies Stage);
    vi.spyOn(shareCardTools, "image").mockResolvedValue(png);
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    URL.createObjectURL = vi.fn(() => "blob:card");
    URL.revokeObjectURL = vi.fn();
});
afterEach(() => {
    vi.restoreAllMocks();
    document.documentElement.classList.remove("dark");
});
async function openDialog() {
    render(<ShareCard {...props} />);
    fireEvent.click(screen.getByRole("link", { name: "Share card" }));
    await act(async () => {});
    fireEvent.click(screen.getByText("Link", { selector: "summary" }));
}
function button(name: string) {
    return screen.getByRole("button", { name });
}
function status() {
    return screen.getByRole("status").textContent;
}
function expandEmbed() {
    fireEvent.click(screen.getByText("Embed", { selector: "summary" }));
}

it("retains the public card link and modified-click navigation", () => {
    render(<ShareCard {...props} />);
    const link = screen.getByRole("link", { name: "Share card" });
    expect(link.getAttribute("href")).toBe(props.cardUrl);
    fireEvent.click(link, { metaKey: true });
    expect(screen.queryByRole("dialog")).toBeNull();
});
it("prepares a high-resolution image for both direct interaction and export", async () => {
    await openDialog();
    expect(screen.getByRole("img").getAttribute("src")).toBe("blob:card");
    expect(
        screen
            .getByRole("link", { name: "Open full-resolution card image" })
            .getAttribute("href"),
    ).toBe("blob:card");
    expect(screen.getByRole("img").getAttribute("draggable")).toBe("true");
    expect(shareCardTools.stage).toHaveBeenCalledWith(address, "standard");
    expect(shareCardTools.image).toHaveBeenCalledWith(
        expect.anything(),
        "standard",
    );
});
it.each(["1:1", "4:5"])(
    "updates the actual image when %s is selected",
    async (aspect) => {
        await openDialog();
        await act(async () => fireEvent.click(button(aspect)));
        expect(button(aspect).getAttribute("aria-pressed")).toBe("true");
        expect(shareCardTools.image).toHaveBeenLastCalledWith(
            expect.anything(),
            aspect,
        );
        expect(screen.getByRole("img").getAttribute("alt")).toContain(aspect);
    },
);
it("copies exactly the image shown in the preview", async () => {
    const copy = vi
        .spyOn(shareCardTools, "copyImage")
        .mockImplementation((blob) => blob.then(() => undefined));
    await openDialog();
    await act(async () => fireEvent.click(button("Copy image")));
    const file = await copy.mock.calls[0][0];
    expect(file.type).toBe("image/png");
    expect(file.size).toBe(png.size);
    expect(status()).toContain("Image copied.");
});
it("shares the prepared image file from the click", async () => {
    const share = vi.spyOn(shareCardTools, "share").mockResolvedValue();
    await openDialog();
    await act(async () => fireEvent.click(button("Share image")));
    expect(share.mock.calls[0][0].files?.[0].name).toBe("mother-vex.png");
    expect(share.mock.calls[0][0].files?.[0].type).toBe("image/png");
});
it("prevents exporting a stale image while the new ratio is rendering", async () => {
    await openDialog();
    vi.mocked(shareCardTools.image).mockReturnValue(new Promise(() => {}));
    await act(async () => fireEvent.click(button("4:5")));
    expect((button("Copy image") as HTMLButtonElement).disabled).toBe(true);
    expect((button("Share image") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("img")).toBeNull();
});
it("offers image downloading when clipboard access fails", async () => {
    vi.spyOn(shareCardTools, "copyImage").mockRejectedValue(
        new Error("denied"),
    );
    await openDialog();
    await act(async () => fireEvent.click(button("Copy image")));
    expect(
        screen
            .getByRole("link", { name: "Download image" })
            .getAttribute("download"),
    ).toBe("mother-vex.png");
    expect(status()).toContain("Download the image");
});
it("retains copy and download on devices without file sharing", async () => {
    vi.mocked(shareCardTools.canShare).mockReturnValue(false);
    await openDialog();
    expect(button("Copy image")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download image" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Share image" })).toBeNull();
});
it("shows the link before copying and keeps it selectable after denial", async () => {
    vi.spyOn(shareCardTools, "copyText").mockRejectedValue(new Error("denied"));
    await openDialog();
    const link = screen.getByLabelText("Link to the card") as HTMLInputElement;
    expect(link.value).toBe(address);
    await act(async () => fireEvent.click(button("Copy link")));
    expect(link.value).toBe(address);
    expect(status()).toContain("Select the text");
});
it("copies the themed public link", async () => {
    const copy = vi.spyOn(shareCardTools, "copyText").mockResolvedValue();
    await openDialog();
    await act(async () => fireEvent.click(button("Copy link")));
    expect(copy).toHaveBeenCalledWith(address);
    expect(status()).toBe("Link copied.");
});
it("shares links through the native sheet", async () => {
    const share = vi.spyOn(shareCardTools, "share").mockResolvedValue();
    await openDialog();
    await act(async () => fireEvent.click(button("Share link")));
    expect(share).toHaveBeenCalledWith({
        url: address,
        title: "Mother Vex – Venom Sisters",
    });
});
it("treats closing the sheet as cancellation and copies on share failure", async () => {
    const share = vi
        .spyOn(shareCardTools, "share")
        .mockRejectedValueOnce(
            Object.assign(new Error("closed"), { name: "AbortError" }),
        )
        .mockRejectedValueOnce(new Error("failed"));
    const copy = vi.spyOn(shareCardTools, "copyText").mockResolvedValue();
    await openDialog();
    await act(async () => fireEvent.click(button("Share link")));
    expect(copy).not.toHaveBeenCalled();
    await act(async () => fireEvent.click(button("Share link")));
    expect(share).toHaveBeenCalledTimes(2);
    expect(copy).toHaveBeenCalledWith(address);
});
it("starts with Embed collapsed and expands the live preview and selectable code", async () => {
    await openDialog();
    expect(
        screen
            .getByText("Embed", { selector: "summary" })
            .parentElement?.hasAttribute("open"),
    ).toBe(false);
    expandEmbed();
    expect(screen.getByTitle("Embed preview").getAttribute("src")).toBe(
        address,
    );
    const copy = vi.spyOn(shareCardTools, "copyText").mockResolvedValue();
    await act(async () => fireEvent.click(button("Copy embed code")));
    expect(copy).toHaveBeenCalledWith(
        embedCode(address, "Mother Vex – Venom Sisters", "", "100%"),
    );
});
it("applies height and width overrides to both the iframe and copied code", async () => {
    await openDialog();
    expandEmbed();
    fireEvent.change(screen.getByLabelText("Width"), {
        target: { value: "640" },
    });
    fireEvent.change(screen.getByLabelText("Height"), {
        target: { value: "720" },
    });
    expect(screen.getByTitle("Embed preview").getAttribute("width")).toBe(
        "640",
    );
    expect(screen.getByTitle("Embed preview").getAttribute("height")).toBe(
        "720",
    );
    expect(
        (screen.getByLabelText("Embed code") as HTMLTextAreaElement).value,
    ).toContain('width="640" height="720"');
});
it("uses the Gyrinx theme initially and applies overrides across every option", async () => {
    document.documentElement.classList.add("dark");
    await openDialog();
    expect(
        (screen.getByLabelText("Link to the card") as HTMLInputElement).value,
    ).toContain("theme=dark");
    await act(async () => fireEvent.click(button("Light")));
    expect(screen.getByRole("img").getAttribute("alt")).toContain(
        "light theme",
    );
    expect(screen.getByTitle("Embed preview").getAttribute("src")).toContain(
        "theme=light",
    );
    expect(
        (screen.getByLabelText("Embed code") as HTMLTextAreaElement).value,
    ).toContain("theme=light");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
});
it("shows only light and dark icons, initially selected from the Gyrinx theme", async () => {
    document.documentElement.classList.add("dark");
    await openDialog();
    expect(button("Dark").getAttribute("aria-pressed")).toBe("true");
    expect(button("Light").getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByText("Gyrinx setting")).toBeNull();
});
it("retries a failed image render", async () => {
    vi.mocked(shareCardTools.image).mockRejectedValueOnce(new Error("broken"));
    await openDialog();
    expect(screen.getByText("The image could not be made.")).toBeTruthy();
    await act(async () => fireEvent.click(button("Try again")));
    expect(screen.getByRole("img")).toBeTruthy();
});
it("discards late renders and releases staged documents and image URLs on close", async () => {
    await openDialog();
    await act(async () => fireEvent.click(button("Close")));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(removed).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:card");
});
it("escapes titles and query parameters in embed attributes", () => {
    expect(
        embedCode(
            "https://x/card/?a=1&theme=dark",
            'Vex "the" <Queen>',
            300,
            480,
        ),
    ).toContain(
        'src="https://x/card/?a=1&amp;theme=dark" title="Vex &quot;the&quot; &lt;Queen&gt;"',
    );
});

it("discards an older theme's image even if it finishes after the current one", async () => {
    let finish!: (blob: Blob) => void;
    vi.mocked(shareCardTools.image).mockReturnValueOnce(
        new Promise((resolve) => {
            finish = resolve;
        }),
    );
    await openDialog();
    await act(async () => fireEvent.click(button("Dark")));
    expect(screen.getByRole("img").getAttribute("alt")).toContain("dark theme");
    const created = vi.mocked(URL.createObjectURL).mock.calls.length;
    await act(async () => finish(png));
    expect(vi.mocked(URL.createObjectURL).mock.calls.length).toBe(created);
    expect(screen.getByRole("img").getAttribute("alt")).toContain("dark theme");
});

it("ignores an old page load failure after an aspect selection", async () => {
    let reject!: (reason: Error) => void;
    vi.mocked(shareCardTools.stage).mockReturnValueOnce(
        new Promise((_resolve, fail) => {
            reject = fail;
        }),
    );
    await openDialog();
    await act(async () => fireEvent.click(button("4:5")));
    await act(async () => reject(new Error("offline")));
    expect(screen.getByRole("img").getAttribute("alt")).toContain("4:5");
    expect(screen.queryByText("The image could not be made.")).toBeNull();
});

it("defaults embed width to 100% and leaves height unset", async () => {
    await openDialog();
    expandEmbed();
    expect((screen.getByLabelText("Width") as HTMLInputElement).value).toBe(
        "100%",
    );
    expect(screen.getByTitle("Embed preview").getAttribute("width")).toBe(
        "100%",
    );
    expect(
        (screen.getByLabelText("Embed code") as HTMLTextAreaElement).value,
    ).not.toContain("height=");
});
it("uses the requested loading label while rendering", async () => {
    vi.mocked(shareCardTools.image).mockReturnValue(new Promise(() => {}));
    await openDialog();
    expect(screen.getByText("Invoking machine spirit…")).toBeTruthy();
});
it("applies a custom image ratio and keeps preset controls independent", async () => {
    await openDialog();
    fireEvent.click(button("Custom"));
    fireEvent.change(screen.getByLabelText("Ratio width"), {
        target: { value: "16" },
    });
    fireEvent.change(screen.getByLabelText("Ratio height"), {
        target: { value: "9" },
    });
    await act(async () => fireEvent.click(button("Apply ratio")));
    expect(shareCardTools.stage).toHaveBeenLastCalledWith(address, "16:9");
    expect(screen.getByRole("img").getAttribute("alt")).toContain("16:9");
    await act(async () => fireEvent.click(button("1:1")));
    expect(button("1:1").getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByLabelText("Ratio width")).toBeNull();
});
it("refuses an invalid custom ratio without replacing the current image", async () => {
    await openDialog();
    fireEvent.click(button("Custom"));
    fireEvent.change(screen.getByLabelText("Ratio height"), {
        target: { value: "0" },
    });
    await act(async () => fireEvent.click(button("Apply ratio")));
    expect(screen.getByRole("alert").textContent).toContain("positive numbers");
    expect(shareCardTools.image).toHaveBeenCalledTimes(1);
});
it.each([
    ["0", "1"],
    ["1", "0"],
    ["", "1"],
    ["NaN", "1"],
    ["1000", "1"],
    ["1", "100"],
])("rejects unsupported ratio %s:%s", (width, height) => {
    expect(customRatio(width, height)).toBeNull();
});
it("accepts decimal and conventional image ratios", () => {
    expect(customRatio("16", "9")).toBe("16:9");
    expect(customRatio("200", "200")).toBe("200:200");
    expect(customRatio("1.5", "1")).toBe("1.5:1");
});

it("starts with Link collapsed", async () => {
    render(<ShareCard {...props} />);
    fireEvent.click(screen.getByRole("link", { name: "Share card" }));
    await act(async () => {});
    expect(
        screen
            .getByText("Link", { selector: "summary" })
            .parentElement?.hasAttribute("open"),
    ).toBe(false);
});
it.each(["75%", "640px", "32rem", "24em"])(
    "passes embed width %s through to code and preview",
    async (width) => {
        await openDialog();
        expandEmbed();
        fireEvent.change(screen.getByLabelText("Width"), {
            target: { value: width },
        });
        const preview = screen.getByTitle("Embed preview") as HTMLIFrameElement;
        expect(preview.getAttribute("width")).toBe(width);
        expect(preview.style.width).toBe(width);
        expect(
            (screen.getByLabelText("Embed code") as HTMLTextAreaElement).value,
        ).toContain(`width="${width}"`);
        expect(
            (screen.getByLabelText("Embed code") as HTMLTextAreaElement).value,
        ).toContain(`style="border:0;width:${width}"`);
    },
);
it("retains unitless pixel widths and escapes pasted embed attributes", () => {
    expect(embedDimensionStyle("640")).toBe("640px");
    const code = embedCode(
        "https://x/card/",
        "Card",
        400,
        '30rem" onload="alert(1)',
    );
    expect(code).not.toContain(' onload="');
    expect(code).toContain("&quot;");
});

it.each(["75%", "480px", "24rem", "18em"])(
    "passes optional embed height %s through to code and preview",
    async (height) => {
        await openDialog();
        expandEmbed();
        fireEvent.change(screen.getByLabelText("Height"), {
            target: { value: height },
        });
        const preview = screen.getByTitle("Embed preview") as HTMLIFrameElement;
        expect(preview.getAttribute("height")).toBe(height);
        expect(preview.style.height).toBe(height);
        const code = (
            screen.getByLabelText("Embed code") as HTMLTextAreaElement
        ).value;
        expect(code).toContain(`height="${height}"`);
        expect(code).toContain(`;height:${height}`);
    },
);
it("removes the embed height completely when the field is cleared", async () => {
    await openDialog();
    expandEmbed();
    const height = screen.getByLabelText("Height") as HTMLInputElement;
    expect(height.value).toBe("");
    fireEvent.change(height, { target: { value: "24rem" } });
    fireEvent.change(height, { target: { value: "" } });
    const preview = screen.getByTitle("Embed preview") as HTMLIFrameElement;
    expect(preview.hasAttribute("height")).toBe(false);
    expect(preview.style.height).toBe("");
    const code = (screen.getByLabelText("Embed code") as HTMLTextAreaElement)
        .value;
    expect(code).not.toContain("height=");
    expect(code).not.toContain("height:");
});
