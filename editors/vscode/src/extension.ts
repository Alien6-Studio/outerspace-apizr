import * as vscode from "vscode";
import * as path from "node:path";
import { EngineClient, EngineError, Json, Response, object } from "./engine";
import { childEnvironment, folderFor, settings, usageAllowed } from "./environment";
import { Documents, EvidenceItem, EvidenceTree, Location, locations, navigate, relativeSource } from "./presentation";
import { stringify } from "./json";
import { Dashboard, captureLabel, sourceReference } from "./dashboard";
import { inspectionLenses, sourceUri } from "./workbench";

export function activate(context: vscode.ExtensionContext) {
    const inspection = new EvidenceTree(), runs = new EvidenceTree(), documents = new Documents();
    const inspectionView = vscode.window.createTreeView("apizr.inspection", { treeDataProvider: inspection });
    const runsView = vscode.window.createTreeView("apizr.runs", { treeDataProvider: runs, canSelectMany: true });
    const dashboard = new Dashboard(vscode.Uri.joinPath(context.extensionUri, "media", "icon.png"));
    const lenses = new vscode.EventEmitter<void>();
    context.subscriptions.push(inspection, runs, inspectionView, runsView, dashboard, lenses, vscode.workspace.registerTextDocumentContentProvider("apizr-result", documents),
        vscode.languages.registerCodeLensProvider({ language: "python", scheme: "file" }, { onDidChangeCodeLenses: lenses.event, provideCodeLenses: inspectionLenses }),
        vscode.workspace.onDidGrantWorkspaceTrust(() => lenses.fire()));
    const clients = new Set<EngineClient>();
    const watchers = new Map<string, vscode.FileSystemWatcher>();
    const timers = new Map<string, ReturnType<typeof setTimeout>>();
    let inspected: vscode.Uri | undefined, stale = false, lastReport: { [key: string]: Json } | undefined;
    let lastInspection: Response | undefined, lastHistory: Response | undefined;
    let recorded: { root: string; location: Location } | undefined;
    let historyFolder: vscode.Uri | undefined;
    let inspectionGeneration = 0, historyGeneration = 0;

    const cancel = () => { for (const client of clients) { client.cancel(); } };
    const reportError = (error: unknown) => {
        const message = error instanceof EngineError ? `${error.code}: ${error.message}` : "operation_failed: Check the selected engine, saved source and operator configuration.";
        void vscode.window.showErrorMessage(`Apizr — ${message}`);
    };
    async function run<T>(uri: vscode.Uri | undefined, project: boolean, title: string, action: (client: EngineClient, signal: AbortSignal) => Promise<T>, progress = true): Promise<T> {
        const folder = folderFor(uri);
        const client = new EngineClient(settings(folder, project));
        const controller = new AbortController();
        clients.add(client);
        const work = async (token?: vscode.CancellationToken) => {
            const subscription = token?.onCancellationRequested(() => controller.abort());
            try { return await action(client, controller.signal); }
            finally {
                subscription?.dispose(); clients.delete(client);
                if (usageAllowed() && client.lastPreview) { lastReport = client.lastPreview; }
                else if (!usageAllowed()) { lastReport = undefined; }
            }
        };
        return progress ? vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: `Apizr: ${title}`, cancellable: true }, (_, token) => work(token)) : work();
    }
    function diagnostics(response: Response): void {
        if (!response.ok) { void vscode.window.showWarningMessage(`Apizr — ${response.diagnostics.map(d => object(d) ? String(d.code) : "operation_failed").join(", ")}`); }
    }
    const activeSource = () => sourceUri();
    async function inspect(context?: unknown): Promise<Response> {
        const selected = sourceUri(context);
        if (!selected || selected.scheme !== "file" || ![".py", ".ipynb"].includes(path.extname(selected.fsPath))) { throw new EngineError("source_required", "Save and select a Python script or notebook before inspection."); }
        const folder = folderFor(selected), config = settings(folder);
        const source = relativeSource(config.cwd, selected.fsPath);
        const document = vscode.workspace.textDocuments.find(d => d.uri.toString() === selected.toString());
        const notebook = vscode.workspace.notebookDocuments.find(d => d.uri.toString() === selected.toString());
        const dirty = document?.isDirty || notebook?.isDirty;
        const generation = ++inspectionGeneration;
        inspected = selected; stale = Boolean(dirty);
        const response = await run(selected, true, "Inspect saved source", (client, signal) => client.request("inspect", { source }, signal));
        if (generation !== inspectionGeneration) { return response; }
        diagnostics(response); lastInspection = response;
        if (response.ok && response.value) {

            const observed = locations(response.value);
            inspection.items = Object.entries(response.value).map(([key, value]) => new EvidenceItem(key, value, `/${key}`, config.cwd, observed));
            inspectionView.description = stale ? "Outdated — saved file inspected; live edits excluded" : dirty ? "Saved file; unsaved changes excluded" : "Saved file";
            inspection.changed();
            await documents.show("inspection", response.value);
            if (dirty) { void vscode.window.showWarningMessage("Apizr inspected the saved file. Unsaved changes were excluded."); }
        } else { await documents.show("inspection-refusal", response as unknown as Json); }
        return response;
    }
    function publicationWatch(folder: vscode.WorkspaceFolder): void {
        const key = folder.uri.toString();
        if (watchers.has(key)) { return; }
        const config = settings(folder);
        const pattern = new vscode.RelativePattern(vscode.Uri.file(path.join(config.cwd, config.store, "runs")), "*.json");
        const watcher = vscode.workspace.createFileSystemWatcher(pattern, false, true, false);
        const refresh = () => {
            const previous = timers.get(key); if (previous) { clearTimeout(previous); }
            timers.set(key, setTimeout(() => { timers.delete(key); void refreshRuns(folder.uri, false).catch(reportError); }, 150));
        };
        watcher.onDidCreate(refresh, undefined, context.subscriptions);
        watcher.onDidDelete(refresh, undefined, context.subscriptions);
        watchers.set(key, watcher);
    }
    async function refreshRuns(uri?: vscode.Uri, progress = true): Promise<Response> {
        const selected = sourceUri(uri);
        const folder = folderFor(selected?.scheme === "file" ? selected : historyFolder);
        const generation = ++historyGeneration;
        const response = await run(folder.uri, true, "Read validated history", (client, signal) => client.request("experiment_list", { limit: 20 }, signal), progress);
        if (generation !== historyGeneration) { return response; }
        diagnostics(response); lastHistory = response; historyFolder = folder.uri;
        runs.items = [];
        if (response.ok && response.value && Array.isArray(response.value.runs)) {
            for (const value of response.value.runs) {
                if (!object(value) || typeof value.run_digest !== "string") { continue; }
                const item = new EvidenceItem(path.basename(sourceReference(value.source)), value);
                item.description = `${String(value.status)} · ${captureLabel(value.capture)} · ${value.run_digest.slice(0, 8)}`;
                item.iconPath = new vscode.ThemeIcon(value.status === "success" ? "pass" : value.status === "failed" ? "error" : "circle-slash");
                item.tooltip = stringify(value, 2);
                item.command = { command: "apizr.showTrackedRun", title: "Show tracked Run", arguments: [value.run_digest, folder.uri] };
                item.contextValue = "apizrRun";
                runs.items.push(item);
            }
            runsView.description = `${String(response.value.matched)} matched / ${String(response.value.total)} validated; up to 20 shown`;
            publicationWatch(folder);
        }
        dashboard.update(response.ok ? response.value ?? undefined : undefined, folder.uri.fsPath);
        runs.changed(); return response;
    }
    async function selectRun(title: string, exclude?: string): Promise<string | undefined> {
        const choices = runs.items.filter(item => object(item.value) && item.value.run_digest !== exclude).map(item => ({ label: item.label as string, description: String(item.description), id: (item.value as { run_digest: string }).run_digest }));
        if (!choices.length) { throw new EngineError("history_required", "Refresh Runs before selecting an experiment."); }
        return (await vscode.window.showQuickPick(choices, { title }))?.id;
    }
    async function showRun(id?: string, uri?: vscode.Uri, showJson = true): Promise<Response | undefined> {
        const selected = id ?? await selectRun("Select a Run"); if (!selected) { return; }
        const response = await run(uri ?? historyFolder ?? activeSource(), true, "Show recorded Run", (client, signal) => client.request("experiment_show", { run_id: selected }, signal));
        diagnostics(response);
        recorded = undefined;
        if (response.ok && response.value && object(response.value.run)) {
            const subject = response.value.run.subject;
            const identity = object(subject) && object(subject.identity) ? subject.identity : subject;
            if (object(identity) && typeof identity.reference === "string") {
                recorded = { root: settings(folderFor(uri ?? historyFolder ?? activeSource())).cwd, location: { source: identity.reference, line: 1, column: 0 } };
            }
        }
        dashboard.select(response.ok ? response.value ?? undefined : undefined);
        if (showJson || !response.ok) { await documents.show("run", (response.value ?? response) as unknown as Json); }
        return response;
    }
    async function compare(runA?: string, runB?: string, uri?: vscode.Uri): Promise<Response | undefined> {
        const selection = runsView.selection;
        const digest = (index: number) => object(selection[index]?.value) ? String((selection[index].value as { run_digest: string }).run_digest) : undefined;
        const first = runA ?? (selection.length === 2 ? digest(0) : await selectRun("Select first Run")); if (!first) { return; }
        const second = runB ?? (selection.length === 2 ? digest(1) : await selectRun("Select second Run", first)); if (!second) { return; }
        const response = await run(uri ?? historyFolder ?? activeSource(), true, "Compare recorded evidence", (client, signal) => client.request("experiment_diff", { run_a: first, run_b: second }, signal));
        diagnostics(response); await documents.show("comparison", (response.value ?? response) as unknown as Json); return response;
    }
    async function telemetry(action: "status" | "preview"): Promise<{ [key: string]: Json }> {
        let result: { [key: string]: Json };
        if (action === "preview" && usageAllowed() && lastReport) { result = lastReport; }
        else if (!vscode.workspace.isTrusted) { result = { collection_enabled: false, transmission_available: false, reason: "workspace_untrusted", payload: JSON.stringify({ schema_version: "apizr.telemetry/v1", context: "vscode", events: [] }) }; }
        else { result = await run(activeSource(), false, "Local telemetry " + action, (client, signal) => client.telemetry(action, signal)); }
        await documents.show("telemetry-" + action, result); return result;
    }
    async function selectEngine(): Promise<void> {
        if (!vscode.workspace.isTrusted) { throw new EngineError("workspace_untrusted", "Trust the workspace before selecting an executable."); }
        const choice = await vscode.window.showQuickPick(["Python interpreter", "Installed apizr executable (including uv tool)"], { title: "Select the engine type in this extension host" });
        if (!choice) { return; }
        const selected = await vscode.window.showOpenDialog({ canSelectFiles: true, canSelectFolders: false, canSelectMany: false, title: "Select the installed engine; no download or installation" });
        if (!selected?.length) { return; }
        const config = vscode.workspace.getConfiguration("apizr");
        const python = choice === "Python interpreter";
        await config.update(python ? "engine.python" : "engine.executable", selected[0].fsPath, vscode.ConfigurationTarget.Global);
        await config.update("engine.mode", python ? "python" : "executable", vscode.ConfigurationTarget.Global);
    }
    function markStale(uri: vscode.Uri): void {
        if (!inspected) { return; }
        const notebook = vscode.workspace.notebookDocuments.find(n => n.uri.toString() === inspected!.toString());
        if (uri.toString() === inspected.toString() || notebook?.getCells().some(c => c.document.uri.toString() === uri.toString())) { stale = true; inspectionView.description = "Outdated — inspect saved file again"; }
    }
    const commands: Record<string, (...args: any[]) => unknown> = {
        openDashboard: () => dashboard.show(),
        openSettings: () => vscode.commands.executeCommand("workbench.action.openSettings", "@ext:alien6-studio.apizr"),
        showTrackedRun: async (id?: string, uri?: vscode.Uri) => {
            const response = await showRun(id, uri, false);
            if (response?.ok) { dashboard.show(); }
            return response;
        },
        inspect, refreshRuns, showRun, compareRuns: compare, openSource: (root?: string, location?: Location) => {
            if (root && location) { return navigate(root, location); }
            if (recorded) { return navigate(recorded.root, recorded.location); }
            throw new EngineError("source_unknown", "Open a Run with a recorded source before navigating; unknown sources are not guessed.");
        }, cancel,
        selectEngine,
        checkEngine: async () => {
            const response = await run(activeSource(), false, "Check installed engine", (client, signal) => client.discover(signal));
            void vscode.window.showInformationMessage(`Apizr engine ${String(response.value?.engine_version)} supports apizr.editor/v1.`);
            return response;
        },
        telemetryStatus: () => telemetry("status"), telemetryPreview: () => telemetry("preview"),
        telemetryEnable: async () => { await vscode.workspace.getConfiguration("apizr").update("telemetry.enabled", true, vscode.ConfigurationTarget.Global); },
        telemetryDisable: async () => { lastReport = undefined; await vscode.workspace.getConfiguration("apizr").update("telemetry.enabled", false, vscode.ConfigurationTarget.Global); cancel(); },
    };
    for (const [name, command] of Object.entries(commands)) {
        context.subscriptions.push(vscode.commands.registerCommand(`apizr.${name}`, async (...args: unknown[]) => { try {
            if (!vscode.workspace.isTrusted && !name.startsWith("telemetry") && !["cancel", "openDashboard", "openSettings"].includes(name)) { throw new EngineError("workspace_untrusted", "Project operations are disabled in Restricted Mode."); }
            return await command(...args);
        } catch (error) { reportError(error); return undefined; } }));
    }
    context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(event => markStale(event.document.uri)));
    context.subscriptions.push(vscode.workspace.onDidChangeNotebookDocument(event => markStale(event.notebook.uri)));
    context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(document => {
        markStale(document.uri);
        if (vscode.workspace.isTrusted && document.uri.scheme === "file" && path.extname(document.uri.fsPath) === ".py" && vscode.workspace.getConfiguration("apizr", document.uri).get("inspectOnSave", false)) { void inspect(document.uri).catch(reportError); }
    }));
    context.subscriptions.push(vscode.workspace.onDidSaveNotebookDocument(notebook => {
        markStale(notebook.uri);
        if (vscode.workspace.isTrusted && notebook.uri.scheme === "file" && vscode.workspace.getConfiguration("apizr", notebook.uri).get("inspectOnSave", false)) { void inspect(notebook.uri).catch(reportError); }
    }));
    context.subscriptions.push(vscode.env.onDidChangeTelemetryEnabled(() => { if (!usageAllowed()) { lastReport = undefined; cancel(); } }));
    context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
        if (event.affectsConfiguration("apizr") || event.affectsConfiguration("telemetry")) {
            lenses.fire();
            if (!usageAllowed()) { lastReport = undefined; }
            cancel();
            if (["apizr.engine", "apizr.project", "apizr.projectRoot", "apizr.operatorPolicy", "apizr.store"].some(key => event.affectsConfiguration(key))) {
                for (const watcher of watchers.values()) { watcher.dispose(); } watchers.clear();
                for (const timer of timers.values()) { clearTimeout(timer); } timers.clear();
                historyGeneration++; historyFolder = undefined; lastHistory = undefined;
                runs.items = []; runsView.description = undefined; runs.changed(); dashboard.clear(); recorded = undefined;
            }
        }
    }));
    context.subscriptions.push({ dispose: () => { cancel(); for (const timer of timers.values()) { clearTimeout(timer); } for (const watcher of watchers.values()) { watcher.dispose(); } documents.clear(); lastReport = undefined; } });
    return { inspect, refreshRuns, showRun, compare, telemetry, state: () => ({ stale, inspection: lastInspection, history: lastHistory, activeProcesses: clients.size, telemetryAllowed: childEnvironment().APIZR_TELEMETRY_ALLOWED }) };
}
