import { spawn, ChildProcess } from "node:child_process";
import { parseJson } from "./json";

export type Json = null | boolean | number | bigint | string | Json[] | { [key: string]: Json };
export type Operation = "capabilities" | "inspect" | "experiment_list" | "experiment_show" | "experiment_diff" | "plan_exposure";
export interface Settings {
    command: string;
    prefix: string[];
    project: string;
    policy: string;
    store: string;
    cwd: string;
    timeoutMs: number;
    env: NodeJS.ProcessEnv;
}
export interface Response {
    schema_version: "apizr.editor-response/v1";
    request_id: string;
    operation: Operation;
    ok: boolean;
    value: { [key: string]: Json } | null;
    diagnostics: Json[];
}
export class EngineError extends Error {
    constructor(readonly code: string, message: string) { super(message); }
}
export function object(value: unknown): value is { [key: string]: Json } {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}
const RESULTS: Record<Operation, string[]> = {
    capabilities: ["apizr.editor-capabilities/v1"], inspect: ["apizr.experiment-inspection/v1"],
    experiment_list: ["apizr.experiment-history/v1", "apizr.experiment-history/v2"],
    experiment_show: ["apizr.experiment-record/v1", "apizr.experiment-record/v2"],
    experiment_diff: ["apizr.experiment-diff/v1", "apizr.experiment-diff/v2"],
    plan_exposure: ["apizr.exposure-plan/v1"],
};
export function admitResponse(raw: string, id: string, operation: Operation): Response {
    let value: unknown;
    try { value = parseJson(raw); } catch { throw new EngineError("invalid_response", "The engine returned unsupported JSON. Use the qualified VS Code host and a compatible installed engine."); }
    if (!object(value) || value.schema_version !== "apizr.editor-response/v1" || value.request_id !== id || value.operation !== operation || typeof value.ok !== "boolean" || !Array.isArray(value.diagnostics) || value.diagnostics.length > 1024 || Object.keys(value).some(k => !["schema_version", "request_id", "operation", "ok", "value", "diagnostics", "exposure_diagnostics"].includes(k)) || (value.ok ? !object(value.value) || !RESULTS[operation].includes(String(value.value.schema_version)) : value.value !== null || value.diagnostics.length === 0)) {
        throw new EngineError("incompatible_engine", "The engine does not support the required editor contract. Install a 0.4.6 development engine supporting apizr.editor/v1.");
    }
    return value as unknown as Response;
}

export class EngineClient {
    private sequence = 0;
    private readonly children = new Set<ChildProcess>();
    private readonly cancellations = new Map<ChildProcess, () => void>();
    lastPreview: { [key: string]: Json } | undefined;
    constructor(readonly settings: Settings) {}
    cancel(): void { for (const abort of this.cancellations.values()) { abort(); } }
    private stop(child: ChildProcess, signal: NodeJS.Signals = "SIGTERM"): void {
        try {
            if (process.platform !== "win32" && child.pid) { process.kill(-child.pid, signal); }
            else { child.kill(signal); }
        } catch { /* A closed process needs no cancellation. */ }
    }
    private execute(args: string[], input: string, signal?: AbortSignal): Promise<string> {
        if (Buffer.byteLength(input) > 65536) { return Promise.reject(new EngineError("request_too_large", "Reduce the editor request to at most 65536 bytes.")); }
        if (signal?.aborted) { return Promise.reject(new EngineError("cancelled", "Apizr request cancelled.")); }
        if (this.children.size >= 4) { return Promise.reject(new EngineError("busy", "Wait for an Apizr request to finish or cancel it.")); }
        return new Promise((resolve, reject) => {
            const child = spawn(this.settings.command, [...this.settings.prefix, ...args], { cwd: this.settings.cwd, env: this.settings.env, shell: false, detached: process.platform !== "win32", stdio: ["pipe", "pipe", "pipe"] });
            this.children.add(child);
            const output: Buffer[] = [], errors: Buffer[] = [];
            let bytes = 0, errorBytes = 0, chunks = 0, settled = false;
            let force: NodeJS.Timeout | undefined;
            const fail = (code: string, message: string) => {
                if (settled) { return; }
                settled = true;
                this.stop(child);
                force = setTimeout(() => this.stop(child, "SIGKILL"), 500);
                reject(new EngineError(code, message));
            };
            const abort = () => fail("cancelled", "Apizr request cancelled.");
            this.cancellations.set(child, abort);
            const deadline = setTimeout(() => fail("timeout", "The engine exceeded the configured deadline. Cancel or inspect a smaller source."), this.settings.timeoutMs);
            signal?.addEventListener("abort", abort, { once: true });
            if (signal?.aborted) { abort(); }
            child.stdout.on("data", (chunk: Buffer) => {
                bytes += chunk.length; chunks++;
                if (bytes > 4194304 || chunks > 4096) { fail("response_too_large", "The engine response exceeds the editor limit."); }
                else if (!settled) { output.push(chunk); }
            });
            child.stderr.on("data", (chunk: Buffer) => {
                errorBytes += chunk.length; chunks++;
                if (errorBytes > 65536 || chunks > 4096) { fail("response_too_large", "The engine diagnostic stream exceeds the editor limit."); }
                else if (!settled) { errors.push(chunk); }
            });
            child.stdin.on("error", () => { /* Exit/error supplies the stable result. */ });
            child.on("error", () => fail("engine_start_failed", "Unable to start the selected engine. Check the absolute interpreter or apizr executable path."));
            child.on("close", code => {
                clearTimeout(deadline); if (force) { clearTimeout(force); }
                signal?.removeEventListener("abort", abort);
                this.children.delete(child);
                this.cancellations.delete(child);
                if (settled) { return; }
                settled = true;
                if (code !== 0 && code !== 2) { reject(new EngineError("engine_failed", "The selected engine could not complete the request. Check its installation and settings.")); return; }
                let stdout: string, stderr: string;
                try { stdout = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(output)); stderr = new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(errors)); }
                catch { reject(new EngineError("invalid_response", "The engine returned invalid UTF-8.")); return; }
                if (this.settings.env.APIZR_TELEMETRY_ALLOWED === "1") {
                    const line = stderr.split("\n").find(s => s.startsWith("APIZR_TELEMETRY_PREVIEW "));
                    if (line) {
                        try {
                            const report: unknown = JSON.parse(line.slice(24));
                            if (object(report) && report.transmission_available === false && typeof report.payload === "string" && Buffer.byteLength(report.payload) <= 16384) { this.lastPreview = report; }
                        } catch { /* Usage previews cannot affect the operation. */ }
                    }
                }
                resolve(stdout);
            });
            child.stdin.end(input);
        });
    }
    private async raw(operation: Operation, args: { [key: string]: Json }, signal?: AbortSignal): Promise<Response> {
        const id = String(++this.sequence);
        const command = ["editor"];
        if (operation !== "capabilities") { command.push("--project", this.settings.project, "--operator-policy", this.settings.policy, "--store", this.settings.store); }
        const raw = await this.execute(command, JSON.stringify({ schema_version: "apizr.editor/v1", request_id: id, operation, arguments: args }), signal);
        return admitResponse(raw, id, operation);
    }
    async discover(signal?: AbortSignal): Promise<Response> {
        const response = await this.raw("capabilities", {}, signal);
        const value = response.value;
        if (!response.ok || !value || value.protocol !== "apizr.editor/v1" || value.max_request_bytes !== 65536 || value.max_response_bytes !== 4194304 || !Array.isArray(value.operations) || !Object.keys(RESULTS).every(op => (value.operations as Json[]).some(item => object(item) && item.name === op && item.read_only === true && Array.isArray(item.result_schemas) && RESULTS[op as Operation].every(schema => (item.result_schemas as Json[]).includes(schema))))) {
            throw new EngineError("incompatible_engine", "Select an engine with all six read-only apizr.editor/v1 operations and the documented bounds.");
        }
        return response;
    }
    async request(operation: Exclude<Operation, "capabilities">, args: { [key: string]: Json } = {}, signal?: AbortSignal): Promise<Response> {
        await this.discover(signal);
        return this.raw(operation, args, signal);
    }
    async telemetry(action: "status" | "preview", signal?: AbortSignal): Promise<{ [key: string]: Json }> {
        const raw = await this.execute(["telemetry", action], "", signal);
        let value: unknown;
        try { value = JSON.parse(raw); } catch { value = null; }
        if (!object(value) || value.transmission_available !== false) { throw new EngineError("incompatible_engine", "Select an engine supporting local-only telemetry controls."); }
        return value;
    }
}
