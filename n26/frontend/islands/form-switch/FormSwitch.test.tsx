import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import cotton from "../../generated/cotton.json";
import { FormSwitch, type FormSwitchProps } from "./FormSwitch";

const props: FormSwitchProps = {
    name: "foundable",
    value: "on",
    checked: false,
    disabled: false,
    accent: true,
    size: "md",
    className: "",
    id: "id_foundable",
};

function Parent({ initial }: { initial?: Partial<FormSwitchProps> }) {
    const label = useRef<HTMLLabelElement>(null);
    const log = useRef<string[]>([]);
    const [hidePlaying, setHidePlaying] = useState(true);
    useEffect(() => {
        const element = label.current!;
        const onChange = (event: Event) => {
            log.current.push("change");
            setHidePlaying((event.target as HTMLInputElement).checked);
        };
        const onCheckedChange = () => {
            log.current.push("checkedChange");
            setHidePlaying((current) => !current);
        };
        element.addEventListener("change", onChange);
        element.addEventListener("checkedChange", onCheckedChange);
        return () => {
            element.removeEventListener("change", onChange);
            element.removeEventListener("checkedChange", onCheckedChange);
        };
    }, []);
    const applied = { ...props, ...initial };
    return (
        <form>
            <label ref={label}>
                <FormSwitch {...applied} />
                <span>Hide gangs already in a campaign</span>
            </label>
            <output data-testid="list">
                {hidePlaying ? "hidden" : "shown"}
            </output>
            <output data-testid="log">{log.current.join(",")}</output>
        </form>
    );
}

describe("FormSwitch", () => {
    it("posts the cotton checkbox only while it is on", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <label htmlFor="id_foundable">
                    Foundable
                    <FormSwitch {...props} />
                </label>
            </form>,
        );
        const form = container.querySelector("form")!;
        const box = form.querySelector(
            'input[name="foundable"]',
        ) as HTMLInputElement;

        expect(box.value).toBe("on");
        expect(box.id).toBe("id_foundable");
        expect(new FormData(form).has("foundable")).toBe(false);

        await user.click(screen.getByRole("switch", { name: "Foundable" }));
        expect(box.checked).toBe(true);
        expect(new FormData(form).get("foundable")).toBe("on");

        await user.click(screen.getByText("Foundable"));
        expect(new FormData(form).has("foundable")).toBe(false);
    });

    it("names the switch from the label and skips the island props script", () => {
        render(
            <label>
                <script type="application/json">
                    {JSON.stringify({ name: "t1", checked: true })}
                </script>
                <FormSwitch {...props} id="" checked name="t1" />
                <span>Your lists only</span>
            </label>,
        );
        const control = screen.getByRole("switch", { name: "Your lists only" });
        expect(control.getAttribute("aria-label")).toBe("Your lists only");
    });

    it("submits a custom value and starts from the server's checked state", () => {
        const { container } = render(
            <form>
                <FormSwitch
                    {...props}
                    checked
                    value="yes"
                    name="staged"
                    id="id_staged"
                />
            </form>,
        );
        const box = container.querySelector(
            'input[name="staged"]',
        ) as HTMLInputElement;
        expect(box.checked).toBe(true);
        expect(
            new FormData(container.querySelector("form")!).get("staged"),
        ).toBe("yes");
        expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe(
            "true",
        );
        const control = screen.getByRole("switch");
        expect(control.className).toContain(cotton.switch.trackChecked);
        expect(control.querySelector("span")!.className).toContain(
            cotton.switch.sizes.md.on,
        );
    });

    it("keeps a parent in step whether the track or the label was clicked", async () => {
        const user = userEvent.setup();
        render(<Parent initial={{ checked: true }} />);

        await user.click(screen.getByRole("switch"));
        expect(screen.getByTestId("log").textContent).toBe(
            "checkedChange,change",
        );
        expect(screen.getByTestId("list").textContent).toBe("shown");
        expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe(
            "false",
        );

        await user.click(screen.getByText("Hide gangs already in a campaign"));
        expect(screen.getByTestId("log").textContent).toBe(
            "checkedChange,change,change",
        );
        expect(screen.getByTestId("list").textContent).toBe("hidden");
    });

    it("uses the size and muted accent classes from the cotton face", () => {
        const { unmount } = render(
            <form>
                <label htmlFor="id_s">
                    Small
                    <FormSwitch {...props} id="id_s" size="sm" />
                </label>
            </form>,
        );
        const control = screen.getByRole("switch", { name: "Small" });
        expect(control.className).toContain(cotton.switch.sizes.sm.track);
        expect(control.className).not.toContain(cotton.switch.sizes.md.track);
        unmount();

        render(
            <form>
                <FormSwitch {...props} checked accent={false} id="id_muted" />
            </form>,
        );
        expect(screen.getByRole("switch").className).toContain(
            cotton.switch.trackCheckedMuted,
        );
    });

    it("does not move a disabled switch", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <FormSwitch {...props} disabled id="id_off" />
            </form>,
        );
        const disabled = screen.getByRole("switch");
        expect(disabled.hasAttribute("disabled")).toBe(true);
        expect(disabled.className).toContain(cotton.switch.disabled);
        await user.click(disabled);
        expect(
            container.querySelector<HTMLInputElement>(
                'input[name="foundable"]',
            )!.checked,
        ).toBe(false);
    });
});
