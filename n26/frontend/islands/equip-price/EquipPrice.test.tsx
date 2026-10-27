import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { mount } from "./entry";
import { EquipPrice, type EquipPriceProps } from "./EquipPrice";
import type { PickGroup, ResolutionGroup } from "./OptionChoices";

const props: EquipPriceProps = {
    field: "sword:price",
    quoted: 35,
    label: "Sword",
    min: 0,
    max: 100000,
};

const groups: PickGroup[] = [
    {
        field: "mount:option:0",
        choose: "one",
        nothingTaken: false,
        options: [
            {
                name: "Launchers",
                value: "0",
                setKey: "launchers",
                price: 25,
                surcharge: 0,
                surchargeLabel: "",
                checked: true,
            },
            {
                name: "Plasma guns",
                value: "1",
                setKey: "plasma",
                price: 40,
                surcharge: 15,
                surchargeLabel: "+15¢",
                checked: false,
            },
            {
                name: "Light guns",
                value: "2",
                setKey: "light",
                price: 20,
                surcharge: -5,
                surchargeLabel: "−5¢",
                checked: false,
            },
        ],
    },
    {
        field: "mount:option:1",
        choose: "one-or-none",
        nothingTaken: true,
        options: [
            {
                name: "Smoke dispenser",
                value: "0",
                setKey: "smoke",
                price: 20,
                surcharge: 20,
                surchargeLabel: "+20¢",
                checked: false,
            },
        ],
    },
];
const purchaseProps: EquipPriceProps = {
    ...props,
    field: "mount:price",
    quoted: 150,
    label: "Mount",
    choices: groups,
    purchase: {
        name: "Mount",
        repeat: false,
        tradePoints: 0,
        exclusive: false,
        buy: { label: "Buy", target: "mount" },
    },
};

const resolutionOf = (groups: PickGroup[]): ResolutionGroup[] =>
    groups.map(({ choose, options }) => ({ choose, options }));

describe("option price previews", () => {
    it("uses the server's first-option default for an unselected required group", () => {
        render(
            <EquipPrice
                changing
                choices={[
                    {
                        ...groups[0],
                        options: groups[0].options.map((option) => ({
                            ...option,
                            checked: false,
                        })),
                    },
                ]}
                before={0}
                held={[]}
                resolution={resolutionOf([groups[0]])}
            />,
        );
        expect(
            screen.getByRole<HTMLInputElement>("radio", { name: "Launchers" })
                .checked,
        ).toBe(true);
        expect(screen.getByRole("status").textContent).toBe(
            "Options charge 25¢",
        );
    });

    it("totals groups and keeps the posted base payment separate", () => {
        const { container } = render(
            <form>
                <EquipPrice {...purchaseProps} />
            </form>,
        );
        const base = screen.getByRole("spinbutton", {
            name: "Base price for Mount",
        });
        expect(screen.getByRole("status").textContent).toBe("Total 150¢");
        fireEvent.click(
            screen.getByRole("radio", { name: "Plasma guns +15¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe("Total 165¢");
        fireEvent.click(
            screen.getByRole("radio", { name: "Smoke dispenser +20¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe("Total 185¢");
        fireEvent.change(base, { target: { value: "140" } });
        expect(screen.getByRole("status").textContent).toBe("Total 175¢");
        const data = new FormData(container.querySelector("form")!);
        expect(data.get("mount:price")).toBe("140");
        expect(data.get("mount:option:0")).toBe("1");
        expect(data.get("mount:option:1")).toBe("0");
        expect(data.get("total")).toBeNull();
        fireEvent.click(screen.getByRole("radio", { name: "None" }));
        fireEvent.click(screen.getByRole("radio", { name: "Launchers" }));
        expect(screen.getByRole("status").textContent).toBe("Total 140¢");
    });

    it("previews cheaper options, an empty base, and negative equipment prices", () => {
        render(<EquipPrice {...purchaseProps} quoted={-10} min={-10} />);
        fireEvent.click(screen.getByRole("radio", { name: "Light guns −5¢" }));
        expect(screen.getByRole("status").textContent).toBe("Total -15¢");
        const base = screen.getByRole("spinbutton");
        fireEvent.change(base, { target: { value: "-5" } });
        expect(screen.getByRole("status").textContent).toBe("Total -10¢");
        fireEvent.change(base, { target: { value: "" } });
        expect(screen.getByRole("status").textContent).toBe("Total -15¢");
    });

    it("adds and removes any-number selections independently", () => {
        const any: PickGroup = {
            ...groups[0],
            choose: "any",
            options: groups[0].options.map((option) => ({
                ...option,
                checked: false,
            })),
        };
        render(<EquipPrice {...purchaseProps} choices={[any]} />);
        fireEvent.click(
            screen.getByRole("checkbox", { name: "Plasma guns +15¢" }),
        );
        fireEvent.click(
            screen.getByRole("checkbox", { name: "Light guns −5¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe("Total 160¢");
        fireEvent.click(
            screen.getByRole("checkbox", { name: "Plasma guns +15¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe("Total 145¢");
    });

    it("shows the change against the held options' full prices", () => {
        render(
            <EquipPrice
                changing
                choices={groups}
                before={25}
                held={["launchers"]}
                resolution={resolutionOf(groups)}
            />,
        );
        expect(screen.getByRole("status").textContent).toBe("No price change");
        fireEvent.click(
            screen.getByRole("radio", { name: "Plasma guns +15¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe(
            "Options charge 15¢",
        );
        fireEvent.click(screen.getByRole("radio", { name: "Light guns −5¢" }));
        expect(screen.getByRole("status").textContent).toBe(
            "Options refund 5¢",
        );
        fireEvent.click(
            screen.getByRole("radio", { name: "Smoke dispenser +20¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe(
            "Options charge 15¢",
        );
    });

    it("retains a price and options edited before React mounts", () => {
        const host = document.createElement("div");
        host.innerHTML =
            '<input type="number" name="mount:price" value="150"><input type="radio" name="mount:option:0" value="1" checked><input type="radio" name="mount:option:1" value="">';
        document.body.appendChild(host);
        host.querySelector<HTMLInputElement>('input[type="number"]')!.value =
            "140";
        host.querySelector<HTMLInputElement>('input[type="radio"]')!.focus();
        let unmount = () => {};
        act(() => {
            unmount = mount(host, purchaseProps);
        });
        expect(screen.getByRole("status").textContent).toBe("Total 155¢");
        expect(document.activeElement).toBe(
            screen.getByRole("radio", { name: "Plasma guns +15¢" }),
        );
        expect(
            screen.getByRole<HTMLInputElement>("radio", {
                name: "Plasma guns +15¢",
            }).checked,
        ).toBe(true);
        act(() => unmount());
        host.remove();
    });

    it("leaves unchanged shared sets alone and includes fixed options in a change", () => {
        render(
            <EquipPrice
                changing
                choices={[groups[0]]}
                before={32}
                held={["launchers", "fixed"]}
                resolution={[
                    ...resolutionOf([groups[0]]),
                    {
                        choose: "one",
                        options: [{ setKey: "launchers", price: 25 }],
                    },
                    { choose: "one", options: [{ setKey: "fixed", price: 7 }] },
                ]}
            />,
        );
        expect(screen.getByRole("status").textContent).toBe("No price change");
        fireEvent.click(
            screen.getByRole("radio", { name: "Plasma guns +15¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe(
            "Options charge 40¢",
        );
    });

    it.each([true, false])(
        "matches settlement when a shared group is fixed: %s",
        (fixed) => {
            const guns: PickGroup = {
                ...groups[0],
                options: groups[0].options.map((option) => ({
                    ...option,
                    checked: option.value === "1",
                })),
            };
            const shared: PickGroup = {
                ...groups[1],
                options: [
                    {
                        ...groups[0].options[0],
                        name: "Extra launchers",
                        checked: false,
                    },
                    {
                        name: "Extra fitting",
                        value: "1",
                        price: 7,
                        surcharge: 7,
                        surchargeLabel: "+7¢",
                        setKey: "extra",
                        checked: true,
                    },
                ],
            };
            render(
                <EquipPrice
                    changing
                    choices={fixed ? [guns] : [guns, shared]}
                    before={fixed ? 65 : 47}
                    held={[fixed ? "launchers" : "extra", "plasma"]}
                    resolution={[
                        ...resolutionOf([guns]),
                        fixed
                            ? {
                                  choose: "one",
                                  options: [{ setKey: "launchers", price: 25 }],
                              }
                            : resolutionOf([shared])[0],
                    ]}
                />,
            );
            expect(screen.getByRole("status").textContent).toBe(
                "No price change",
            );
            fireEvent.click(screen.getByRole("radio", { name: "Launchers" }));
            expect(screen.getByRole("status").textContent).toBe(
                "Options refund 15¢",
            );
            if (!fixed) {
                fireEvent.click(
                    screen.getByRole("radio", { name: "Extra launchers" }),
                );
                expect(screen.getByRole("status").textContent).toBe(
                    "Options charge 3¢",
                );
                fireEvent.click(screen.getByRole("radio", { name: "None" }));
                expect(screen.getByRole("status").textContent).toBe(
                    "Options refund 22¢",
                );
            }
        },
    );
});

describe("ordered resolution and loading focus", () => {
    it("includes paid equipment refunds only when its option departs", () => {
        render(
            <EquipPrice
                changing
                choices={groups}
                before={25}
                held={["launchers"]}
                resolution={resolutionOf(groups)}
                refunds={[
                    {
                        setKey: "launchers",
                        entries: [{ key: "sight", paid: 20 }],
                    },
                ]}
            />,
        );
        expect(screen.getByRole("status").textContent).toBe("No price change");
        fireEvent.click(
            screen.getByRole("radio", { name: "Plasma guns +15¢" }),
        );
        expect(screen.getByRole("status").textContent).toBe(
            "Options refund 5¢",
        );
        fireEvent.click(screen.getByRole("radio", { name: "Launchers" }));
        expect(screen.getByRole("status").textContent).toBe("No price change");
    });

    it("refunds a paid descendant shared by departing options once", () => {
        const picked = [
            groups[0],
            {
                ...groups[1],
                options: groups[1].options.map((option) => ({
                    ...option,
                    checked: true,
                })),
            },
        ];
        render(
            <EquipPrice
                changing
                choices={picked}
                before={45}
                held={["launchers", "smoke"]}
                resolution={resolutionOf(picked)}
                refunds={[
                    {
                        setKey: "launchers",
                        entries: [{ key: "shared", paid: 20 }],
                    },
                    { setKey: "smoke", entries: [{ key: "shared", paid: 20 }] },
                ]}
            />,
        );
        fireEvent.click(screen.getByRole("radio", { name: "Light guns −5¢" }));
        fireEvent.click(screen.getByRole("radio", { name: "None" }));
        expect(screen.getByRole("status").textContent).toBe(
            "Options refund 45¢",
        );
    });

    it.each([true, false])(
        "resolves a named shared set with fixed group first: %s",
        (fixedFirst) => {
            const optional: PickGroup = {
                ...groups[1],
                options: [
                    {
                        ...groups[0].options[0],
                        name: "Shared guns",
                        checked: false,
                    },
                    {
                        name: "Fitting",
                        value: "1",
                        setKey: "fitting",
                        price: 7,
                        surcharge: 7,
                        surchargeLabel: "+7¢",
                        checked: true,
                    },
                ],
            };
            const fixed: ResolutionGroup = {
                choose: "one",
                options: [{ setKey: "launchers", price: 25 }],
            };
            const resolution = fixedFirst
                ? [fixed, ...resolutionOf([optional])]
                : [...resolutionOf([optional]), fixed];
            render(
                <EquipPrice
                    changing
                    choices={[optional]}
                    before={32}
                    held={["launchers", "fitting"]}
                    resolution={resolution}
                />,
            );
            expect(screen.getByRole("status").textContent).toBe(
                "No price change",
            );
            fireEvent.click(screen.getByRole("radio", { name: "Shared guns" }));
            expect(screen.getByRole("status").textContent).toBe(
                fixedFirst ? "Options refund 7¢" : "Options charge 18¢",
            );
        },
    );

    it("restores a focused option when the change dialog mounts", () => {
        const host = document.createElement("div");
        host.innerHTML =
            '<input type="radio" name="mount:option:0" value="0" checked><input type="radio" name="mount:option:1" value="" checked>';
        document.body.appendChild(host);
        host.querySelector<HTMLInputElement>("input")!.focus();
        let unmount = () => {};
        act(() => {
            unmount = mount(host, {
                changing: true,
                choices: groups,
                before: 25,
                held: ["launchers"],
                resolution: resolutionOf(groups),
            });
        });
        expect(document.activeElement).toBe(
            screen.getByRole("radio", { name: "Launchers" }),
        );
        act(() => unmount());
        host.remove();
    });
});

describe("EquipPrice", () => {
    it("starts at the quote and names the box", () => {
        render(<EquipPrice {...props} />);
        const box = screen.getByRole("spinbutton", { name: "Price for Sword" });
        expect(box.getAttribute("name")).toBe("sword:price");
        expect(box.getAttribute("value")).toBe("35");
        expect(box.getAttribute("min")).toBe("0");
        expect(box.getAttribute("max")).toBe("100000");
        expect(document.querySelector("[title]")).toBeNull();
    });

    it("shows a higher price to the left of the box", () => {
        render(<EquipPrice {...props} />);
        fireEvent.change(screen.getByRole("spinbutton"), {
            target: { value: "50" },
        });
        const box = screen.getByRole("spinbutton");
        const delta = document.querySelector("[title]");
        expect(delta?.textContent).toBe("+15¢");
        expect(delta?.getAttribute("title")).toBe("Listed at 35¢");
        expect(
            delta!.compareDocumentPosition(box) &
                Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
    });

    it("shows a lower price to the left of the box", () => {
        render(<EquipPrice {...props} />);
        fireEvent.change(screen.getByRole("spinbutton"), {
            target: { value: "8" },
        });
        expect(document.querySelector("[title]")?.textContent).toBe("−27¢");
    });

    it("says nothing when the box is cleared or returned to the quote", () => {
        render(<EquipPrice {...props} />);
        const box = screen.getByRole("spinbutton");
        fireEvent.change(box, { target: { value: "" } });
        expect(document.querySelector("[title]")).toBeNull();
        fireEvent.change(box, { target: { value: "35" } });
        expect(document.querySelector("[title]")).toBeNull();
    });

    it("lets gear priced below nothing open at that price", () => {
        render(
            <EquipPrice
                {...props}
                field="brittle:price"
                quoted={-10}
                label="Reduced bone density"
                min={-10}
            />,
        );
        const box = screen.getByRole("spinbutton", {
            name: "Price for Reduced bone density",
        });
        expect(box.getAttribute("value")).toBe("-10");
        expect(box.getAttribute("min")).toBe("-10");
        expect(document.querySelector("[title]")).toBeNull();
        fireEvent.change(box, { target: { value: "-5" } });
        expect(document.querySelector("[title]")?.textContent).toBe("+5¢");
    });
});

describe("mounting over the server-drawn box", () => {
    it("keeps a figure typed before the module loaded", () => {
        const host = document.createElement("div");
        host.innerHTML = '<input type="number" name="sword:price" value="35">';
        document.body.appendChild(host);
        (host.querySelector("input") as HTMLInputElement).value = "8";

        let unmount: () => void = () => {};
        act(() => {
            unmount = mount(host, props);
        });

        const box = host.querySelector<HTMLInputElement>(
            'input[name="sword:price"]',
        );
        expect(box?.value).toBe("8");
        expect(host.textContent).toContain("−27¢");
        expect(host.textContent?.indexOf("−27¢")).toBeLessThan(
            host.innerHTML.indexOf("sword:price"),
        );
        act(() => unmount());
        host.remove();
    });

    it("puts focus back when the box was being typed into", () => {
        const host = document.createElement("div");
        host.innerHTML = '<input type="number" name="sword:price" value="35">';
        document.body.appendChild(host);
        const original = host.querySelector("input") as HTMLInputElement;
        original.value = "8";
        original.focus();

        let unmount: () => void = () => {};
        act(() => {
            unmount = mount(host, props);
        });

        const box = host.querySelector<HTMLInputElement>(
            'input[name="sword:price"]',
        );
        expect(box?.value).toBe("8");
        expect(document.activeElement).toBe(box);
        act(() => unmount());
        host.remove();
    });

    it("leaves focus alone when another control is active", () => {
        const other = document.createElement("button");
        other.textContent = "Buy";
        document.body.appendChild(other);
        other.focus();
        const host = document.createElement("div");
        host.innerHTML = '<input type="number" name="sword:price" value="35">';
        document.body.appendChild(host);

        let unmount: () => void = () => {};
        act(() => {
            unmount = mount(host, props);
        });

        expect(document.activeElement).toBe(other);
        act(() => unmount());
        host.remove();
        other.remove();
    });

    it("keeps an emptied box empty", () => {
        render(<EquipPrice {...props} initial="" />);
        expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
            "",
        );
    });
});
