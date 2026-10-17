import * as path from "node:path";
import * as fs from "node:fs/promises";
import { constants } from "node:fs";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { EngineClient, EngineError, Settings } from "./engine";

export interface EngineSpec {
    schema_version: "apizr.vscode-engine/v1";
    version: string;
    protocol: "apizr.editor/v1";
    source: { kind: "git"; commit: string } | { kind: "pypi" };
}
export interface InstalledEngine { command: string; prefix: string[]; }
export function requirement(spec: EngineSpec): string {
    if (spec.schema_version !== "apizr.vscode-engine/v1" || spec.protocol !== "apizr.editor/v1" || !/^\d+\.\d+\.\d+$/.test(spec.version)) { throw new EngineError("invalid_engine_spec", "The bundled engine descriptor is invalid."); }
    if (spec.source.kind === "git" && /^[a-f0-9]{40}$/.test(spec.source.commit)) {
        return `outerspace-apizr[notebook] @ git+https://github.com/Alien6-Studio/outerspace-apizr.git@${spec.source.commit}`;
    }
    if (spec.source.kind === "pypi") { return `outerspace-apizr[notebook]==${spec.version}`; }
    throw new EngineError("invalid_engine_spec", "Only a pinned official Apizr source is supported.");
}

/** Owns only installer processes; never uses a shell or the project directory. */
export async function installationCommand(command: string, args: string[], cwd: string, env: NodeJS.ProcessEnv, signal: AbortSignal, timeout = 300000): Promise<string> {
    if (signal.aborted) { throw new EngineError("cancelled", "CLI installation cancelled."); }
    return new Promise((resolve, reject) => {
        const child = spawn(command, args, { cwd, env, shell: false, detached: process.platform !== "win32", stdio: ["ignore", "pipe", "pipe"] });
        const output: Buffer[] = [];
        let bytes = 0, failure: EngineError | undefined, force: ReturnType<typeof setTimeout> | undefined;
        const stop = (signal: NodeJS.Signals) => { try { if (child.pid) { process.kill(process.platform === "win32" ? child.pid : -child.pid, signal); } } catch { /* Already reaped. */ } };
        const fail = (error: EngineError) => {
            if (failure) { return; } failure = error; stop("SIGTERM");
            force = setTimeout(() => stop("SIGKILL"), 500);
        };
        const cancel = () => fail(new EngineError("cancelled", "CLI installation cancelled."));
        const deadline = setTimeout(() => fail(new EngineError("installation_timeout", "CLI installation exceeded five minutes. Retry or select an existing engine.")), timeout);
        signal.addEventListener("abort", cancel, { once: true });
        if (signal.aborted) { cancel(); }
        const consume = (chunk: Buffer, keep: boolean) => {
            bytes += chunk.length;
            if (bytes > 1048576) { fail(new EngineError("installation_output_limit", "The installer exceeded its output limit.")); }
            else if (keep && !failure) { output.push(chunk); }
        };
        child.stdout.on("data", chunk => consume(chunk, true)); child.stderr.on("data", chunk => consume(chunk, false));
        child.on("error", () => fail(new EngineError("installer_start_failed", "Cannot start the Python installer. Install Python 3.11–3.15 or select an existing CLI.")));
        child.on("close", code => {
            if (failure) { stop("SIGKILL"); }
            clearTimeout(deadline); if (force) { clearTimeout(force); } signal.removeEventListener("abort", cancel);
            if (failure) { reject(failure); }
            else if (code !== 0) { reject(new EngineError("installation_failed", "The installer failed. Check Python, Git and network access, then retry or select an existing engine.")); }
            else { resolve(Buffer.concat(output).toString("utf8").trim()); }
        });
    });
}

export class ManagedEngine {
    private pending?: Promise<InstalledEngine>;
    private controller?: AbortController;
    private readonly identity: string;
    constructor(private readonly storage: string, private readonly spec: EngineSpec, private readonly env: NodeJS.ProcessEnv) {
        this.identity = createHash("sha256").update(requirement(spec)).digest("hex");
    }
    async installed(): Promise<InstalledEngine | undefined> {
        try {
            const marker = JSON.parse(await fs.readFile(path.join(this.storage, "engine.json"), "utf8"));
            if (marker.identity !== this.identity || typeof marker.directory !== "string" || !/^engine-[a-zA-Z0-9-]+$/.test(marker.directory)) { return; }
            const command = path.join(this.storage, marker.directory, "bin", "python");
            await fs.access(command, constants.X_OK);
            return { command, prefix: ["-I", "-B", "-m", "apizr.cli"] };
        } catch { return; }
    }
    install(report: (message: string) => void, signal: AbortSignal): Promise<InstalledEngine> {
        if (this.pending) { return this.pending; }
        this.controller = new AbortController();
        const cancel = () => this.controller?.abort(); signal.addEventListener("abort", cancel, { once: true });
        if (signal.aborted) { cancel(); }
        this.pending = this.prepare(report, this.controller.signal).finally(() => { signal.removeEventListener("abort", cancel); this.pending = undefined; this.controller = undefined; });
        return this.pending;
    }
    cancel(): void { this.controller?.abort(); }
    private async prepare(report: (message: string) => void, signal: AbortSignal): Promise<InstalledEngine> {
        if (signal.aborted) { throw new EngineError("cancelled", "CLI installation cancelled."); }
        const existing = await this.installed(); if (existing) { return existing; }
        await fs.mkdir(this.storage, { recursive: true, mode: 0o700 });
        const directory = await fs.mkdtemp(path.join(this.storage, "engine-"));
        const marker = path.join(this.storage, `engine-${randomUUID()}.json`);
        try {
            report("Finding Python 3.11–3.15");
            let interpreter: string | undefined;
            for (const name of ["python3.14", "python3.13", "python3.12", "python3.11", "python3.15", "python3"]) {
                for (const entry of (this.env.PATH ?? "").split(path.delimiter).filter(path.isAbsolute)) {
                    const candidate = path.join(entry, name);
                    try {
                        await fs.access(candidate, constants.X_OK);
                        const selected = await installationCommand(candidate, ["-I", "-B", "-c", "import sys; print(sys.executable if (3,11) <= sys.version_info[:2] < (3,16) else '')"], directory, this.env, signal, 10000);
                        if (path.isAbsolute(selected) && !/[\r\n\x00]/.test(selected)) { interpreter = selected; break; }
                    } catch (error) { if (signal.aborted) { throw error; } }
                }
                if (interpreter) { break; }
            }
            if (!interpreter) { throw new EngineError("python_required", "Install Python 3.11–3.15 in this extension host, or select an existing Apizr engine."); }
            report("Creating the managed CLI environment");
            await installationCommand(interpreter, ["-I", "-B", "-m", "venv", directory], directory, this.env, signal);
            const command = path.join(directory, "bin", "python");
            report(`Installing Apizr ${this.spec.version} and notebook support`);
            await installationCommand(command, ["-I", "-B", "-m", "pip", "--isolated", "install", "--disable-pip-version-check", "--no-input", "--quiet", "--index-url", "https://pypi.org/simple", requirement(this.spec)], directory, this.env, signal);
            report("Checking the installed CLI protocol");
            const engine = { command, prefix: ["-I", "-B", "-m", "apizr.cli"] };
            const settings: Settings = { ...engine, cwd: directory, project: "", policy: "", store: ".apizr/experiments/v1", timeoutMs: 30000, env: this.env };
            const response = await new EngineClient(settings).discover(signal);
            if (response.value?.engine_version !== this.spec.version) { throw new EngineError("incompatible_engine", "The installed CLI version does not match this extension."); }
            if (signal.aborted) { throw new EngineError("cancelled", "CLI installation cancelled."); }
            await fs.writeFile(marker, JSON.stringify({ identity: this.identity, directory: path.basename(directory) }), { mode: 0o600, flag: "wx" });
            await fs.rename(marker, path.join(this.storage, "engine.json"));
            return engine;
        } catch (error) {
            await fs.rm(directory, { recursive: true, force: true }); await fs.rm(marker, { force: true }); throw error;
        }
    }
}
