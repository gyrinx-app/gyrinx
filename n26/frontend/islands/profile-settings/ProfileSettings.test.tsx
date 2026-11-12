import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProfileSettings, type ProfileSettingsProps } from "./ProfileSettings";

const props: ProfileSettingsProps = {
    actionUrl: "/profile/settings/",
    csrfToken: "token",
    snapshot: "signed",
    colour: "",
    colours: ["ink", "red", "blue"],
    links: ["", "", ""],
    instagram: "",
    discord: "",
    discordUserId: "",
    location: "",
    extraLinks: [],
    removeExtraLinks: false,
    pictureUrl: "",
    cropMax: 1600,
    errors: {},
    open: false,
    conflict: false,
    reloadUrl: "/profile/",
    removePicture: false,
};

beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
    };
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
    };
});
afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete window.GyrinxImageCrop;
});

async function open() {
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Profile settings" }));
    return user;
}

describe("profile settings", () => {
    it("opens picture editing from the avatar and returns focus on cancel", async () => {
        const slot = document.createElement("div");
        slot.id = "profile-picture-slot";
        document.body.append(slot);
        try {
            render(<ProfileSettings {...props} />);
            const user = userEvent.setup();
            const trigger = screen.getByRole("button", {
                name: "Edit profile picture",
            });
            await user.click(trigger);
            expect(document.activeElement).toBe(
                screen.getByLabelText("Profile picture"),
            );
            await user.click(screen.getByRole("button", { name: "Cancel" }));
            expect(screen.queryByRole("dialog")).toBeNull();
            expect(document.activeElement).toBe(trigger);
        } finally {
            slot.remove();
        }
    });
    it("opens the shared editor directly from the cog with three links, two social accounts and a location", async () => {
        render(<ProfileSettings {...props} />);
        await open();
        expect(screen.queryByRole("menu")).toBeNull();
        const dialog = screen.getByRole("dialog");
        expect(within(dialog).getAllByRole("textbox")).toHaveLength(7);
        expect(dialog.querySelector("form")?.getAttribute("enctype")).toBe(
            "multipart/form-data",
        );
        expect(screen.getByRole("radio", { name: "Default" })).toBeTruthy();
    });

    it("keeps a chosen palette colour and the three submitted link names", async () => {
        render(<ProfileSettings {...props} />);
        const user = await open();
        await user.type(
            screen.getByLabelText("Link 1"),
            "https://example.org/crew",
        );
        await user.click(screen.getByRole("radio", { name: "Blue" }));
        expect(
            (screen.getByRole("radio", { name: "Blue" }) as HTMLInputElement)
                .checked,
        ).toBe(true);
        const form = screen.getByRole("dialog").querySelector("form")!;
        expect(new FormData(form).get("link_0")).toBe(
            "https://example.org/crew",
        );
        expect(new FormData(form).get("link_2")).toBe("");
    });

    it("discards unsaved edits on Cancel and restores trigger focus", async () => {
        render(<ProfileSettings {...props} />);
        const user = await open();
        await user.type(
            screen.getByLabelText("Link 1"),
            "https://example.org/draft",
        );
        await user.click(screen.getByRole("button", { name: "Cancel" }));
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Profile settings" }),
        );
        await open();
        expect(
            (screen.getByLabelText("Link 1") as HTMLInputElement).value,
        ).toBe("");
    });

    it("opens server field errors without discarding the submitted links", () => {
        render(
            <ProfileSettings
                {...props}
                open
                links={["bad", "", "", "", ""]}
                errors={{
                    link_0: [
                        "Enter a link starting with http:// or https://, or an email address.",
                    ],
                }}
            />,
        );
        expect(
            (screen.getByLabelText("Link 1") as HTMLInputElement).value,
        ).toBe("bad");
        expect(
            screen.getByLabelText("Link 1").getAttribute("aria-invalid"),
        ).toBe("true");
    });

    it("requires a reload after a revision conflict", () => {
        render(
            <ProfileSettings
                {...props}
                open
                conflict
                errors={{ __all__: ["Your profile changed in another tab."] }}
            />,
        );
        expect(
            (screen.getByRole("button", { name: "Save" }) as HTMLButtonElement)
                .disabled,
        ).toBe(true);
        expect(
            screen
                .getByRole("link", { name: "Reload profile" })
                .getAttribute("href"),
        ).toBe("/profile/");
    });

    it("keeps a stable busy submit button while the browser saves the native form", async () => {
        render(<ProfileSettings {...props} open />);
        const submit = screen.getByRole("button", { name: "Save" });
        const form = submit.closest("form")!;
        form.addEventListener("submit", (event) => event.preventDefault());
        fireEvent.submit(form);
        expect(submit.getAttribute("aria-busy")).toBe("true");
        expect(submit.textContent).toBe("Save");
    });
    it("waits for a real crop area before enabling confirmation", () => {
        vi.stubGlobal("URL", {
            createObjectURL: () => "blob:picture",
            revokeObjectURL: vi.fn(),
        });
        vi.stubGlobal(
            "requestAnimationFrame",
            (callback: FrameRequestCallback) => {
                callback(0);
                return 1;
            },
        );
        vi.stubGlobal("cancelAnimationFrame", vi.fn());
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
            drawImage: vi.fn(),
        } as unknown as CanvasRenderingContext2D);
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 160;
        let area = { width: 0, height: 0 };
        let update = () => {};
        const create = vi.fn(
            (
                _picture: HTMLImageElement,
                _ratio: number,
                onCrop?: () => void,
            ) => {
                update = onCrop!;
                return {
                    destroy: vi.fn(),
                    getData: () => area,
                    getCroppedCanvas: () => canvas,
                };
            },
        );
        window.GyrinxImageCrop = { create };
        const rendered = render(<ProfileSettings {...props} open />);
        fireEvent.change(screen.getByLabelText("Profile picture"), {
            target: {
                files: [
                    new File(["image"], "sample.png", { type: "image/png" }),
                ],
            },
        });
        expect(screen.getByAltText("Picture to crop").getAttribute("src")).toBe(
            "blob:picture",
        );
        const confirm = screen.getByRole("button", {
            name: "Use this crop",
        }) as HTMLButtonElement;
        expect(confirm.disabled).toBe(true);
        act(update);
        expect(confirm.disabled).toBe(true);
        area = { width: 600, height: 600 };
        act(update);
        expect(confirm.disabled).toBe(false);
        expect(create).toHaveBeenCalledWith(
            expect.any(HTMLImageElement),
            1,
            expect.any(Function),
        );
        rendered.unmount();
        expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:picture");
    });
});

it("submits location and fixed social account fields and discards their drafts on Cancel", async () => {
    render(<ProfileSettings {...props} />);
    const user = await open();
    const location = screen.getByLabelText("Location") as HTMLInputElement;
    await user.type(location, "W".repeat(21));
    expect(location.value).toBe("W".repeat(20));
    await user.clear(location);
    await user.type(location, "Nottingham, UK");
    await user.type(screen.getByLabelText("Instagram handle"), "@ash_road");
    await user.type(screen.getByLabelText("Discord handle"), "@ash.road");
    await user.type(
        screen.getByLabelText("Discord user ID"),
        "123456789012345678",
    );
    const data = new FormData(
        screen.getByRole("dialog").querySelector("form")!,
    );
    expect(data.get("location")).toBe("Nottingham, UK");
    expect(data.get("instagram")).toBe("@ash_road");
    expect(data.get("discord")).toBe("@ash.road");
    expect(data.get("discord_user_id")).toBe("123456789012345678");
    expect(data.has("link_3")).toBe(false);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await open();
    for (const label of [
        "Location",
        "Instagram handle",
        "Discord handle",
        "Discord user ID",
    ]) {
        expect((screen.getByLabelText(label) as HTMLInputElement).value).toBe(
            "",
        );
    }
});

it("rejects markup in a crop URL before it reaches the image or Cropper", () => {
    vi.stubGlobal("URL", {
        createObjectURL: () => 'blob:picture" onerror="alert(1)',
        revokeObjectURL: vi.fn(),
    });
    const create = vi.fn();
    window.GyrinxImageCrop = { create };
    render(<ProfileSettings {...props} open />);
    fireEvent.change(screen.getByLabelText("Profile picture"), {
        target: {
            files: [new File(["image"], "picture.png", { type: "image/png" })],
        },
    });
    expect(
        screen.getByAltText("Picture to crop").getAttribute("src"),
    ).toBeNull();
    expect(create).not.toHaveBeenCalled();
});
