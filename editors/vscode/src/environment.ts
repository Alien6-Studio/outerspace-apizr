import * as vscode from "vscode";
import * as path from "node:path";
import { InstalledEngine } from "./installation";
import { EngineError, Settings } from "./engine";

export function usageAllowed(): boolean {
    return vscode.env.isTelemetryEnabled && vscode.workspace.getConfiguration("telemetry").get("telemetryLevel", "all") === "all" && vscode.workspace.getConfiguration("apizr").get("telemetry.enabled", false) && process.env.APIZR_TELEMETRY !== "0" && (process.env.APIZR_TELEMETRY_ALLOWED ?? "1") === "1" && ["", "0", "false"].includes((process.env.CI ?? "").toLowerCase()) && process.env.APIZR_SERVED_PROCESS !== "1" && process.env.APIZR_EXPERIMENT_RUNNER !== "1";
}
export function childEnvironment(): NodeJS.ProcessEnv {
    const allowed = usageAllowed();
    const env: NodeJS.ProcessEnv = { ...process.env, APIZR_TELEMETRY: allowed ? "1" : "0", APIZR_TELEMETRY_ALLOWED: allowed ? "1" : "0", APIZR_TELEMETRY_CONTEXT: "vscode", APIZR_TELEMETRY_PREVIEW: "1" };
    delete env.PYTHONPATH; delete env.PYTHONHOME;
    return env;
}
export function folderFor(uri?: vscode.Uri): vscode.WorkspaceFolder {
    const folder = uri?.scheme === "file" ? vscode.workspace.getWorkspaceFolder(uri) : vscode.workspace.workspaceFolders?.length === 1 ? vscode.workspace.workspaceFolders[0] : undefined;
    if (!folder || folder.uri.scheme !== "file") { throw new EngineError("workspace_required", "Open one native project folder, or select a source in the intended workspace folder. Virtual workspaces are unsupported."); }
    return folder;
}
export function settings(folder: vscode.WorkspaceFolder, projectRequired = true, managed?: InstalledEngine): Settings {
    if (!vscode.workspace.isTrusted) { throw new EngineError("workspace_untrusted", "Trust this workspace before starting an engine. Apizr launches no engine in Restricted Mode."); }
    if (process.platform === "win32") { throw new EngineError("unsupported_environment", "This extension currently qualifies native Linux and macOS engines. Use a Linux SSH/Dev Container workspace for Windows clients."); }
    const config = vscode.workspace.getConfiguration("apizr", folder.uri);
    const mode = config.get<string>("engine.mode", "managed");
    const command = mode === "managed" ? managed?.command ?? "" : config.get<string>(mode === "python" ? "engine.python" : "engine.executable", "");
    if (!["managed", "python", "executable"].includes(mode) || !path.isAbsolute(command) || /[\x00-\x1f]/.test(command)) { throw new EngineError("engine_required", "Use Apizr: Install CLI or Select engine, or set an absolute apizr.engine.python / apizr.engine.executable path in this extension host."); }
    const project = path.resolve(folder.uri.fsPath, config.get<string>("project", "apizr.toml"));
    const policy = config.get<string>("operatorPolicy", "");
    const store = config.get<string>("store", ".apizr/experiments/v1");
    if (projectRequired && (!path.isAbsolute(policy) || /[\x00-\x1f]/.test(project + policy))) { throw new EngineError("policy_required", "Select an absolute apizr.operatorPolicy granting source.analyze and the exact history.read store for Runs."); }
    if (!store || path.isAbsolute(store) || store.split(/[\\/]/).some(p => p === ".." || p === "." || p === "") || /[\\:\x00-\x1f]/.test(store)) { throw new EngineError("invalid_store", "Use a project-relative store with no traversal or empty components; it must match the operator history grant."); }
    const timeout = config.get<number>("timeoutMs", 30000);
    if (!Number.isInteger(timeout) || timeout < 500 || timeout > 120000) { throw new EngineError("invalid_deadline", "Set apizr.timeoutMs between 500 and 120000."); }
    const selectedRoot = config.get<string>("projectRoot", "");
    const root = selectedRoot ? path.resolve(folder.uri.fsPath, selectedRoot) : path.dirname(project);
    return { command, prefix: mode === "managed" ? managed!.prefix : mode === "python" ? ["-I", "-B", "-m", "apizr.cli"] : [], project, policy, store, cwd: root, timeoutMs: timeout, env: childEnvironment() };
}
