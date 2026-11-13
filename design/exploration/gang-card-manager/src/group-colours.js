import cotton from "./cotton.json";

export const groupColours = [
    { name: "No colour", value: "none", token: null },
    ...cotton.colours.map((colour) => ({
        ...colour,
        value: colour.name.toLowerCase(),
    })),
];
