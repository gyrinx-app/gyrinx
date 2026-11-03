import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
    embedCode,
    ShareCard,
    shareCardTools,
    type ShareCardProps,
    type Stage,
} from "./ShareCard";

const props: ShareCardProps = {
    name: "Mother Vex",
    gang: "Venom Sisters",
    cardUrl: "/n26/fighters/1/card/",
};
const address = new URL(props.cardUrl, window.location.href).href;

let removed: ReturnType<typeof vi.fn<() => void>>;

beforeEach(() => {
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
    removed = vi.fn<() => void>();
    vi.spyOn(shareCardTools, "stage").mockResolvedValue({
        card: document.createElement("div"),
        height: 333,
        remove: removed,
    } satisfies Stage);
    URL.createObjectURL = vi.fn(() => "blob:picture");
    URL.revokeObjectURL = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

async function openDialog() {
    render(<ShareCard {...props} />);
    fireEvent.click(screen.getByRole("link", { name: "Share card" }));
    // Let the staged card settle, so the embed has its measured height.
    await act(async () => {});
}

function status() {
    return screen.getByRole("status").textContent;
}

it("is a link to the card's page, named and titled Share card", () => {
    render(<ShareCard {...props} />);

    const link = screen.getByRole("link", { name: "Share card" });

    expect(link.getAttribute("href")).toBe(props.cardUrl);
    expect(link.getAttribute("title")).toBe("Share card");
    expect(screen.queryByRole("dialog")).toBeNull();
});

it("leaves a modified click to the browser", () => {
    render(<ShareCard {...props} />);

    fireEvent.click(screen.getByRole("link", { name: "Share card" }), {
        metaKey: true,
    });

    expect(screen.queryByRole("dialog")).toBeNull();
});

it("copies embed code sized to the card", async () => {
    const copy = vi
        .spyOn(shareCardTools, "copyText")
        .mockResolvedValue(undefined);
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Embed HTML" })),
    );

    expect(shareCardTools.stage).toHaveBeenCalledWith(address);
    expect(copy).toHaveBeenCalledWith(
        embedCode(address, "Mother Vex – Venom Sisters", 333),
    );
    expect(status()).toBe(
        "HTML copied. Paste it where your website takes embed code.",
    );
});

it("shows the code to copy by hand when the browser refuses", async () => {
    vi.spyOn(shareCardTools, "copyText").mockRejectedValue(new Error("denied"));
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Embed HTML" })),
    );

    expect(
        (screen.getByLabelText("Embed code") as HTMLTextAreaElement).value,
    ).toContain(`src="${address}"`);
    expect(status()).toMatch(/did not allow the copy/);
});

it("copies a picture of the card", async () => {
    const blob = new Blob(["png"], { type: "image/png" });
    vi.spyOn(shareCardTools, "picture").mockResolvedValue(blob);
    const copy = vi
        .spyOn(shareCardTools, "copyImage")
        .mockImplementation((png) => png.then(() => undefined));
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Copy image" })),
    );

    await expect(copy.mock.calls[0][0]).resolves.toBe(blob);
    expect(status()).toBe("Image copied. Paste it into a message or document.");
});

it("offers the picture as a download when the browser refuses", async () => {
    vi.spyOn(shareCardTools, "picture").mockResolvedValue(
        new Blob(["png"], { type: "image/png" }),
    );
    vi.spyOn(shareCardTools, "copyImage").mockRejectedValue(
        new Error("denied"),
    );
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Copy image" })),
    );

    const download = screen.getByRole("link", { name: "Download picture" });
    expect(download.getAttribute("href")).toBe("blob:picture");
    expect(download.getAttribute("download")).toBe("mother-vex.png");
});

it("says so when the picture cannot be made", async () => {
    vi.spyOn(shareCardTools, "picture").mockRejectedValue(new Error("broken"));
    vi.spyOn(shareCardTools, "copyImage").mockImplementation((png) =>
        png.then(() => undefined),
    );
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Copy image" })),
    );

    expect(status()).toBe("The picture could not be made. Try again.");
    expect(screen.queryByRole("link", { name: "Download picture" })).toBeNull();
});

it("closes, and clears away the staged card", async () => {
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Close" })),
    );

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(removed).toHaveBeenCalled();
});

it("escapes the title it writes into the embed code", () => {
    expect(embedCode("https://x/card/", 'Vex "the" <Queen> & co', 300)).toBe(
        '<iframe src="https://x/card/" title="Vex &quot;the&quot; &lt;Queen&gt; &amp; co" width="100%" height="300" style="border:0" loading="lazy"></iframe>',
    );
});

function abort() {
    return Object.assign(new Error("closed"), { name: "AbortError" });
}

it("copies the link where there is no share sheet", async () => {
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(false);
    const copy = vi
        .spyOn(shareCardTools, "copyText")
        .mockResolvedValue(undefined);
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Share link" })),
    );

    expect(copy).toHaveBeenCalledWith(address);
    expect(status()).toBe("Link copied.");
});

it("shows the link to copy by hand when the browser refuses", async () => {
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(false);
    vi.spyOn(shareCardTools, "copyText").mockRejectedValue(new Error("denied"));
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Share link" })),
    );

    expect(
        (screen.getByLabelText("Link to the card") as HTMLTextAreaElement)
            .value,
    ).toBe(address);
});

it("opens the share sheet with the card's link", async () => {
    vi.spyOn(shareCardTools, "canShare").mockImplementation(
        (data) => !data.files,
    );
    const share = vi.spyOn(shareCardTools, "share").mockResolvedValue();
    const copy = vi.spyOn(shareCardTools, "copyText");
    await openDialog();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Share link" })),
    );

    expect(share).toHaveBeenCalledWith({
        url: address,
        title: "Mother Vex – Venom Sisters",
    });
    expect(copy).not.toHaveBeenCalled();
});

it("says nothing when the share sheet is closed, and copies when it fails", async () => {
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    vi.spyOn(shareCardTools, "picture").mockResolvedValue(
        new Blob(["png"], { type: "image/png" }),
    );
    const share = vi
        .spyOn(shareCardTools, "share")
        .mockRejectedValueOnce(abort())
        .mockRejectedValueOnce(new Error("broken"));
    const copy = vi
        .spyOn(shareCardTools, "copyText")
        .mockResolvedValue(undefined);
    await openDialog();
    const button = screen.getByRole("button", { name: "Share link" });

    await act(async () => fireEvent.click(button));
    expect(copy).not.toHaveBeenCalled();
    expect(status()).toBe("");

    await act(async () => fireEvent.click(button));
    expect(share).toHaveBeenCalledTimes(2);
    expect(copy).toHaveBeenCalledWith(address);
});

it("leaves out Share picture where the device cannot share files", async () => {
    vi.spyOn(shareCardTools, "canShare").mockImplementation(
        (data) => !data.files,
    );
    const picture = vi.spyOn(shareCardTools, "picture");
    await openDialog();

    expect(screen.queryByRole("button", { name: "Share picture" })).toBeNull();
    expect(picture).not.toHaveBeenCalled();
});

it("makes the picture as the dialog opens and shares it as a file", async () => {
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    vi.spyOn(shareCardTools, "picture").mockResolvedValue(
        new Blob(["png"], { type: "image/png" }),
    );
    const share = vi.spyOn(shareCardTools, "share").mockResolvedValue();
    await openDialog();
    // The stage settles first, then the picture.
    await act(async () => {});

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Share picture" })),
    );

    const data = share.mock.calls[0][0];
    expect(data.title).toBe("Mother Vex – Venom Sisters");
    expect(data.files?.[0].name).toBe("mother-vex.png");
    expect(data.files?.[0].type).toBe("image/png");
});

it("keeps Share picture off until the picture is made", async () => {
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    vi.spyOn(shareCardTools, "picture").mockReturnValue(new Promise(() => {}));
    await openDialog();

    expect(
        (
            screen.getByRole("button", {
                name: "Share picture",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});

it("says so when the picture cannot be shared", async () => {
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    vi.spyOn(shareCardTools, "picture").mockResolvedValue(
        new Blob(["png"], { type: "image/png" }),
    );
    vi.spyOn(shareCardTools, "share").mockRejectedValue(new Error("broken"));
    await openDialog();
    await act(async () => {});

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Share picture" })),
    );

    expect(status()).toBe(
        "The picture could not be shared. Use Copy image instead.",
    );
});

it("leaves out Copy image on a phone, whose share sheet copies", async () => {
    vi.spyOn(shareCardTools, "touchScreen").mockReturnValue(true);
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    vi.spyOn(shareCardTools, "picture").mockResolvedValue(
        new Blob(["png"], { type: "image/png" }),
    );
    vi.spyOn(shareCardTools, "share").mockRejectedValue(new Error("broken"));
    await openDialog();
    await act(async () => {});

    expect(screen.queryByRole("button", { name: "Copy image" })).toBeNull();

    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Share picture" })),
    );
    expect(status()).toBe("The picture could not be shared. Try again.");
});

it("keeps Copy image on a phone that cannot share pictures", async () => {
    vi.spyOn(shareCardTools, "touchScreen").mockReturnValue(true);
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(false);
    await openDialog();

    expect(screen.getByRole("button", { name: "Copy image" })).toBeTruthy();
});

it("keeps Copy image on a computer that can share pictures", async () => {
    vi.spyOn(shareCardTools, "touchScreen").mockReturnValue(false);
    vi.spyOn(shareCardTools, "canShare").mockReturnValue(true);
    vi.spyOn(shareCardTools, "picture").mockReturnValue(new Promise(() => {}));
    await openDialog();

    expect(screen.getByRole("button", { name: "Copy image" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Share picture" })).toBeTruthy();
});
