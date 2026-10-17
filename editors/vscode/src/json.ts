// Presentation codec only. Scientific validation and comparison remain in Python.
type NativeJSON = {
    parse(text: string, reviver: (this: object, key: string, value: unknown, context?: { source: string }) => unknown): unknown;
    rawJSON(text: string): unknown;
};
const native = JSON as unknown as NativeJSON;
const numericTokens = new WeakMap<object, Map<string, string>>();

export function parseJson(text: string): unknown {
    return native.parse(text, function (key, value, context) {
        if (typeof value === "number") {
            if (!context?.source || typeof native.rawJSON !== "function" || context.source.length > 128 || !Number.isFinite(value)) {
                throw new Error("The extension host must support lossless JSON numeric tokens. Update to the qualified VS Code version.");
            }
            let tokens = numericTokens.get(this);
            if (!tokens) { tokens = new Map(); numericTokens.set(this, tokens); }
            tokens.set(key, context.source);
            if (!Number.isSafeInteger(value) && /^-?\d+$/.test(context.source)) { return BigInt(context.source); }
        }
        return value !== null && typeof value === "object" ? Object.freeze(value) : value;
    });
}
export function numberToken(parent: object, key: string): string | undefined {
    return numericTokens.get(parent)?.get(key);
}
export function stringify(value: unknown, space?: number): string {
    return JSON.stringify(value, function (key, item: unknown) {
        const token = numberToken(this, key);
        if (token !== undefined) { return native.rawJSON(token); }
        if (typeof item === "bigint") { return native.rawJSON(item.toString()); }
        return item;
    }, space);
}
