import { createPortal } from "react-dom";
import { useEffect, useId, useRef, useState } from "react";
import {
    Alert,
    Button,
    ColourPicker,
    Dialog,
    Field,
    FormActions,
    Input,
    Icon,
    TickListOption,
} from "../../ui";

type Cropper = {
    getData: () => { width: number; height: number };
    destroy: () => void;
    getCroppedCanvas: (options: {
        maxWidth?: number;
        maxHeight?: number;
        width?: number;
        height?: number;
        imageSmoothingQuality?: string;
    }) => HTMLCanvasElement;
};
declare global {
    interface Window {
        GyrinxImageCrop?: {
            create: (
                picture: HTMLImageElement,
                ratio: number,
                onCrop?: () => void,
            ) => Cropper;
        };
    }
}

export type ProfileSettingsProps = {
    actionUrl: string;
    csrfToken: string;
    snapshot: string;
    colour: string;
    colours: string[];
    links: string[];
    instagram: string;
    discord: string;
    discordUserId: string;
    location: string;
    extraLinks: string[];
    removeExtraLinks: boolean;
    pictureUrl: string;
    cropMax: number;
    errors: Record<string, string[]>;
    open: boolean;
    conflict: boolean;
    reloadUrl: string;
    removePicture: boolean;
};

export function ProfileSettings(props: ProfileSettingsProps) {
    const id = useId();
    const [open, setOpen] = useState(props.open);
    const [pictureOpened, setPictureOpened] = useState(false);
    const pictureSlot = document.getElementById("profile-picture-slot");
    const [links, setLinks] = useState(props.links);
    const [instagram, setInstagram] = useState(props.instagram);
    const [discord, setDiscord] = useState(props.discord);
    const [discordUserId, setDiscordUserId] = useState(props.discordUserId);
    const [location, setLocation] = useState(props.location);
    const [removeExtraLinks, setRemoveExtraLinks] = useState(
        props.removeExtraLinks,
    );
    const [colour, setColour] = useState(props.colour);
    const [pending, setPending] = useState(false);
    const [removePicture, setRemovePicture] = useState(props.removePicture);
    const [cropFile, setCropFile] = useState<File | null>(null);
    const [previewUrl, setPreviewUrl] = useState(props.pictureUrl);
    const [problem, setProblem] = useState("");
    const [encoding, setEncoding] = useState(false);
    const [cropReady, setCropReady] = useState(false);
    const input = useRef<HTMLInputElement>(null);
    const picture = useRef<HTMLImageElement>(null);
    const preview = useRef<HTMLCanvasElement>(null);
    const cropper = useRef<Cropper | null>(null);
    const submitted = useRef(false);
    const staged = useRef<File | null>(null);
    const stagedUrl = useRef("");

    useEffect(() => {
        if (open && pictureOpened) input.current?.focus();
    }, [open, pictureOpened]);

    useEffect(() => {
        function restore(event: PageTransitionEvent) {
            if (event.persisted && submitted.current) window.location.reload();
        }
        window.addEventListener("pageshow", restore);
        return () => window.removeEventListener("pageshow", restore);
    }, []);

    useEffect(
        () => () => {
            if (stagedUrl.current) URL.revokeObjectURL(stagedUrl.current);
        },
        [],
    );
    useEffect(() => {
        if (!cropFile || !picture.current) return;
        if (!window.GyrinxImageCrop) {
            setProblem(
                "The picture cropper could not load. Reload the page to try again.",
            );
            return;
        }
        setCropReady(false);
        const url = URL.createObjectURL(cropFile);
        const image = picture.current;
        image.onerror = () =>
            setProblem("The picture could not be read. Choose another image.");
        image.src = url;
        let frame = 0;
        function draw() {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
                const canvas = preview.current;
                const source = cropper.current?.getCroppedCanvas({
                    width: 160,
                    height: 160,
                });
                const area = cropper.current?.getData();
                if (
                    canvas &&
                    source &&
                    source.width > 0 &&
                    source.height > 0 &&
                    area &&
                    area.width > 0 &&
                    area.height > 0
                ) {
                    canvas.getContext("2d")?.drawImage(source, 0, 0, 160, 160);
                    setCropReady(true);
                }
            });
        }
        cropper.current = window.GyrinxImageCrop.create(image, 1, draw);
        return () => {
            cancelAnimationFrame(frame);
            image.onerror = null;
            cropper.current?.destroy();
            cropper.current = null;
            URL.revokeObjectURL(url);
        };
    }, [cropFile]);

    function restoreInput(file: File | null) {
        if (!input.current) return;
        const transfer = new DataTransfer();
        if (file) transfer.items.add(file);
        input.current.files = transfer.files;
    }
    function cancelCrop() {
        restoreInput(staged.current);
        setCropFile(null);
        setProblem("");
    }
    function confirmCrop() {
        const canvas = cropper.current?.getCroppedCanvas({
            maxWidth: props.cropMax,
            maxHeight: props.cropMax,
            imageSmoothingQuality: "high",
        });
        if (!canvas || canvas.width === 0 || canvas.height === 0) {
            setProblem("The picture could not be read. Choose another image.");
            return;
        }
        setEncoding(true);
        canvas.toBlob(
            (blob) => {
                setEncoding(false);
                if (!blob) {
                    setProblem(
                        "The picture could not be read. Choose another image.",
                    );
                    return;
                }
                const file = new File([blob], "profile.jpg", {
                    type: "image/jpeg",
                });
                restoreInput(file);
                staged.current = file;
                if (stagedUrl.current) URL.revokeObjectURL(stagedUrl.current);
                stagedUrl.current = URL.createObjectURL(file);
                setPreviewUrl(stagedUrl.current);
                setRemovePicture(false);
                setCropFile(null);
            },
            "image/jpeg",
            0.9,
        );
    }
    function dismiss() {
        if (cropFile) {
            cancelCrop();
            return;
        }
        setOpen(false);
        setProblem("");
        setLinks(props.links);
        setInstagram(props.instagram);
        setDiscord(props.discord);
        setDiscordUserId(props.discordUserId);
        setLocation(props.location);
        setRemoveExtraLinks(props.removeExtraLinks);
        setColour(props.colour);
        setRemovePicture(false);
        setPreviewUrl(props.pictureUrl);
        staged.current = null;
        if (stagedUrl.current) URL.revokeObjectURL(stagedUrl.current);
        stagedUrl.current = "";
    }

    return (
        <>
            {pictureSlot &&
                createPortal(
                    <button
                        type="button"
                        id={`${id}-avatar`}
                        aria-label="Edit profile picture"
                        title="Edit profile picture"
                        className="absolute inset-0 rounded-full cursor-pointer focus-ring"
                        onClick={() => {
                            setPictureOpened(true);
                            setOpen(true);
                        }}
                    />,
                    pictureSlot,
                )}
            <Button
                id={`${id}-menu`}
                aria-label="Profile settings"
                title="Profile settings"
                variant="ghost"
                size="sm"
                onClick={() => {
                    setPictureOpened(false);
                    setOpen(true);
                }}
            >
                <Icon name="cog" className="size-5" />
            </Button>
            {open && (
                <Dialog
                    title={
                        cropFile ? "Crop profile picture" : "Profile settings"
                    }
                    returnFocusId={
                        pictureOpened ? `${id}-avatar` : `${id}-menu`
                    }
                    pending={pending || encoding}
                    onDismiss={dismiss}
                    onSubmit={(event) => {
                        if (cropFile || props.conflict) {
                            event.preventDefault();
                            return;
                        }
                        submitted.current = true;
                        setPending(true);
                    }}
                    formProps={{
                        method: "post",
                        action: props.actionUrl,
                        encType: "multipart/form-data",
                    }}
                >
                    <input
                        type="hidden"
                        name="csrfmiddlewaretoken"
                        value={props.csrfToken}
                    />
                    <input
                        type="hidden"
                        name="snapshot"
                        value={props.snapshot}
                    />
                    <div className="space-y-5" hidden={!!cropFile}>
                        {(props.errors.__all__ || props.conflict) && (
                            <Alert tone="error" dismissible={false}>
                                {props.errors.__all__?.join(" ")}
                                {props.conflict && (
                                    <a
                                        className="ml-1 underline"
                                        href={props.reloadUrl}
                                    >
                                        Reload profile
                                    </a>
                                )}
                            </Alert>
                        )}
                        <Field
                            label="Profile picture"
                            htmlFor={`${id}-picture`}
                            errors={props.errors.picture || []}
                            description="Choose an image up to 10 MB. Your picture is shown as a circle."
                        >
                            {previewUrl && !removePicture && (
                                <img
                                    src={previewUrl}
                                    alt="Current profile picture"
                                    className="mb-3 size-20 rounded-full object-cover"
                                />
                            )}
                            <Input
                                id={`${id}-picture`}
                                ref={input}
                                name="picture"
                                type="file"
                                accept="image/*"
                                onChange={(event) => {
                                    const file = event.target.files?.[0];
                                    if (!file) return;
                                    setProblem("");
                                    if (file.size > 10 * 1024 * 1024) {
                                        setProblem(
                                            "Select a picture up to 10 MB.",
                                        );
                                        restoreInput(staged.current);
                                        return;
                                    }
                                    setCropReady(false);
                                    setCropFile(file);
                                }}
                            />
                        </Field>
                        {previewUrl && (
                            <Button
                                size="sm"
                                onClick={() => {
                                    setRemovePicture(!removePicture);
                                    staged.current = null;
                                    restoreInput(null);
                                }}
                            >
                                {removePicture
                                    ? "Keep picture"
                                    : "Remove picture"}
                            </Button>
                        )}
                        <input
                            type="hidden"
                            name="remove_picture"
                            value={removePicture ? "on" : ""}
                        />
                        <Field
                            label="Location"
                            htmlFor={`${id}-location`}
                            errors={props.errors.location || []}
                            description="Your location is public. Leave blank to show “None specified”."
                        >
                            <Input
                                name="location"
                                value={location}
                                maxLength={120}
                                onChange={(event) =>
                                    setLocation(event.target.value)
                                }
                            />
                        </Field>
                        <fieldset className="space-y-3">
                            <legend className="font-semibold">
                                Social links
                            </legend>
                            <p className="text-sm text-muted">
                                Add up to three links or email addresses, plus
                                your Instagram and Discord handles. Start links
                                with http:// or https://. These are public.
                            </p>
                            {links.map((link, index) => (
                                <Field
                                    key={index}
                                    label={`Link ${index + 1}`}
                                    htmlFor={`${id}-link-${index}`}
                                    errors={props.errors[`link_${index}`] || []}
                                >
                                    <Input
                                        name={`link_${index}`}
                                        value={link}
                                        onChange={(event) =>
                                            setLinks(
                                                links.map((v, i) =>
                                                    i === index
                                                        ? event.target.value
                                                        : v,
                                                ),
                                            )
                                        }
                                    />
                                </Field>
                            ))}
                            {props.extraLinks.length > 0 && (
                                <div className="space-y-2 text-sm">
                                    <p className="text-muted">
                                        Your additional saved links are kept
                                        unless you remove them.
                                    </p>
                                    <ul>
                                        {props.extraLinks.map((link) => (
                                            <li
                                                key={link}
                                                className="break-all"
                                            >
                                                {link}
                                            </li>
                                        ))}
                                    </ul>
                                    <TickListOption
                                        name="remove_extra_links"
                                        value="on"
                                        checked={removeExtraLinks}
                                        onChange={setRemoveExtraLinks}
                                        label="Remove additional saved links"
                                    />
                                </div>
                            )}
                            <Field
                                label="Instagram handle"
                                htmlFor={`${id}-instagram`}
                                errors={props.errors.instagram || []}
                                description="Enter your handle, with or without @."
                            >
                                <Input
                                    name="instagram"
                                    value={instagram}
                                    maxLength={31}
                                    autoCapitalize="none"
                                    autoCorrect="off"
                                    onChange={(event) =>
                                        setInstagram(event.target.value)
                                    }
                                />
                            </Field>
                            <Field
                                label="Discord handle"
                                htmlFor={`${id}-discord`}
                                errors={props.errors.discord || []}
                                description="Enter your handle, with or without @."
                            >
                                <Input
                                    name="discord"
                                    value={discord}
                                    maxLength={33}
                                    autoCapitalize="none"
                                    autoCorrect="off"
                                    onChange={(event) =>
                                        setDiscord(event.target.value)
                                    }
                                />
                            </Field>
                            <Field
                                label="Discord user ID"
                                htmlFor={`${id}-discord-id`}
                                errors={props.errors.discord_user_id || []}
                                description="Optional. To link your profile, enable Developer Mode in Discord and use Copy User ID on your profile. Without an ID, your handle is shown as text."
                            >
                                <Input
                                    name="discord_user_id"
                                    value={discordUserId}
                                    inputMode="numeric"
                                    maxLength={20}
                                    onChange={(event) =>
                                        setDiscordUserId(event.target.value)
                                    }
                                />
                            </Field>
                        </fieldset>
                        <ColourPicker
                            name="colour"
                            label="Profile colour"
                            colours={props.colours}
                            value={colour}
                            onChange={setColour}
                        />
                        {props.errors.colour && (
                            <Alert tone="error">
                                {props.errors.colour.join(" ")}
                            </Alert>
                        )}
                    </div>
                    {cropFile && (
                        <div className="space-y-4">
                            <p className="text-sm text-muted">
                                Drag the crop or its corners. The preview shows
                                your circular profile picture.
                            </p>
                            <div className="n26-crop-stage n26-crop-circle">
                                <img ref={picture} alt="Picture to crop" />
                            </div>
                            <canvas
                                ref={preview}
                                width={160}
                                height={160}
                                aria-label="Circular crop preview"
                                role="img"
                                className="mx-auto size-24 rounded-full"
                            />
                        </div>
                    )}
                    {problem && (
                        <Alert tone="error" dismissible={false}>
                            {problem}
                        </Alert>
                    )}
                    <FormActions>
                        <Button
                            onClick={dismiss}
                            disabled={pending || encoding}
                        >
                            {cropFile ? "Cancel crop" : "Cancel"}
                        </Button>
                        {cropFile ? (
                            <Button
                                variant="success"
                                onClick={confirmCrop}
                                busy={encoding || !cropReady}
                                disabled={encoding || !cropReady || !!problem}
                            >
                                Use this crop
                            </Button>
                        ) : (
                            <Button
                                type="submit"
                                variant="success"
                                busy={pending}
                                disabled={pending || props.conflict}
                            >
                                Save
                            </Button>
                        )}
                    </FormActions>
                </Dialog>
            )}
        </>
    );
}
