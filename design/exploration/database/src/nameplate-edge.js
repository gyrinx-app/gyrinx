// Name-seeded polygon with shallow pixel depths to keep the tear clear of text.
export function nameplateEdge(name, bottomOnly = false) {
    let seed = 2166136261;
    for (const character of name.normalize("NFC")) {
        seed = Math.imul(seed ^ character.codePointAt(0), 16777619);
    }
    const random = () => {
        seed += 0x6d2b79f5;
        let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
        value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
        return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };
    const edge = (bottom) => {
        let drift = 0;
        return Array.from({ length: 49 }, (_, index) => {
            if (index % 6 === 0) drift = random() * 1.8;
            const x =
                index === 0 || index === 48
                    ? (index / 48) * 100
                    : ((index + (random() - 0.5) * 0.9) / 48) * 100;
            const nick = random() < 0.12 ? random() * 1.6 : 0;
            const depth = (0.3 + drift + random() * 1.6 + nick).toFixed(2);
            return `${x.toFixed(2)}% ${bottom ? `calc(100% - ${depth}px)` : `${depth}px`}`;
        });
    };
    const top = bottomOnly ? ["0% 0", "100% 0"] : edge(false);
    return `polygon(${[...top, ...edge(true).reverse()].join(",")})`;
}
