import { createRequire } from "node:module";
import { realpathSync } from "node:fs";
import { isAbsolute, resolve, sep } from "node:path";

// Bare imports of these packages. A parent checkout's copy is not a fallback:
// Vite would parse it, including a half-written development build.
const CHECKOUT_PACKAGE = /^(react-dom|react|scheduler)(\/.*)?$/;

const resolved = new Map();

export function resolveCheckoutModule(checkout, specifier) {
    if (!CHECKOUT_PACKAGE.test(specifier) || isAbsolute(specifier)) {
        return null;
    }

    const root = realpathSync(checkout);
    const cacheKey = `${root}\0${specifier}`;
    const cached = resolved.get(cacheKey);
    if (cached !== undefined) {
        return cached;
    }

    const require = createRequire(resolve(root, "package.json"));
    let fromPackage;
    try {
        fromPackage = require.resolve(specifier);
    } catch {
        throw new Error(
            `Could not resolve ${specifier} from ${root}. ` +
                "Run npm ci --no-audit --no-fund in this checkout. " +
                "Do not install into a parent checkout.",
        );
    }

    const real = realpathSync(fromPackage);
    if (real !== root && !real.startsWith(`${root}${sep}`)) {
        throw new Error(
            `${specifier} resolved to ${real}, outside this checkout (${root}). ` +
                `Remove ${resolve(root, "node_modules")}, then run ` +
                "npm ci --no-audit --no-fund in this checkout. " +
                "Do not edit the other checkout's node_modules.",
        );
    }

    resolved.set(cacheKey, real);
    return real;
}
