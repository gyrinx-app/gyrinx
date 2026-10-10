import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { PoolRoll, type PoolRollProps } from "./PoolRoll";
import { mount } from "./entry";

const props: PoolRollProps = {
    count: {
        label: "Number to roll",
        helpText:
            "Choose how many to add to the unclaimed pool, up to 100 at a time.",
        value: "9",
        errors: [],
    },
    rolled: {
        label: "Your own roll",
        helpText: "Optional. Enter a dice roll you have already made.",
        value: "",
        errors: [],
    },
    ranges: ["A D66 roll is 11 to 66."],
};

function inputs() {
    return {
        count: screen.getByRole("spinbutton", {
            name: "Number to roll",
        }) as HTMLInputElement,
        rolled: screen.getByRole("spinbutton", {
            name: "Your own roll",
        }) as HTMLInputElement,
    };
}

describe("campaign pool roll", () => {
    it("sets quantity to one as the manual roll is typed and submits both fields", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <PoolRoll {...props} />
            </form>,
        );
        const { count, rolled } = inputs();
        expect(count.value).toBe("9");
        await user.type(rolled, "3");
        expect(count.value).toBe("1");
        expect(count.readOnly).toBe(true);
        await user.type(rolled, "4");
        await user.type(count, "2");
        const data = new FormData(view.container.querySelector("form")!);
        expect(data.get("count")).toBe("1");
        expect(data.get("rolled")).toBe("34");
        expect(screen.getByText(/Clear ‘Your own roll’/)).toBeTruthy();
    });

    it("allows a larger quantity again after the manual roll is cleared", async () => {
        const user = userEvent.setup();
        render(<PoolRoll {...props} />);
        const { count, rolled } = inputs();
        await user.type(rolled, "34");
        await user.clear(rolled);
        expect(count.readOnly).toBe(false);
        expect(count.value).toBe("1");
        await user.clear(count);
        await user.type(count, "12");
        expect(count.value).toBe("12");
        expect(rolled.value).toBe("");
    });

    it("syncs pasted values and retains server errors and dice guidance", () => {
        render(
            <PoolRoll
                {...props}
                rolled={{
                    ...props.rolled,
                    errors: ["You cannot roll 7 on a D66."],
                }}
            />,
        );
        const { count, rolled } = inputs();
        fireEvent.input(rolled, { target: { value: "34" } });
        expect(count.value).toBe("1");
        expect(screen.getByText("You cannot roll 7 on a D66.")).toBeTruthy();
        expect(rolled.getAttribute("aria-invalid")).toBe("true");
        expect(
            screen.getByText(props.ranges[0]).parentElement?.id,
        ).toBeTruthy();
        expect(rolled.getAttribute("aria-describedby")).toContain(
            screen.getByText(props.ranges[0]).parentElement?.id,
        );
    });

    it("normalises a manual roll on a refused dialog without discarding its value", () => {
        render(
            <PoolRoll {...props} rolled={{ ...props.rolled, value: "7" }} />,
        );
        expect(inputs().count.value).toBe("1");
        expect(inputs().rolled.value).toBe("7");
    });

    it("preserves edits and focus made before the island mounts", async () => {
        const host = document.createElement("div");
        host.className = "space-y-5";
        host.innerHTML =
            '<input name="count" value="12"><input name="rolled" value="34">';
        document.body.append(host);
        const oldRoll =
            host.querySelector<HTMLInputElement>('[name="rolled"]')!;
        oldRoll.focus();
        let dispose: () => void;
        await act(async () => {
            dispose = mount(host, props);
        });
        await waitFor(() =>
            expect(
                host.querySelector<HTMLInputElement>('[name="count"]')?.value,
            ).toBe("1"),
        );
        expect(
            host.querySelector<HTMLInputElement>('[name="rolled"]')?.value,
        ).toBe("34");
        expect(document.activeElement).toBe(
            host.querySelector('[name="rolled"]'),
        );
        await act(async () => {
            dispose!();
        });
        host.remove();
    });
});
