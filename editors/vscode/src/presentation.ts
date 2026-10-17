import * as vscode from "vscode";
import * as path from "node:path";
import * as fs from "node:fs/promises";
import { EngineError, Json, object } from "./engine";
import { numberToken, stringify } from "./json";

export interface Location { source: string; line: number; column: number; cell_index?: number; cell_line?: number; }
export class EvidenceItem extends vscode.TreeItem {
    constructor(label: string, readonly value?: Json, readonly pointer = "", readonly root?: string, readonly locations = new Map<string, Location>(), token?: string) {
        const children = value !== null && typeof value === "object" && Object.keys(value).length > 0;
        super(label, children ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
        const location = locations.get(pointer);
        if (root && location) { this.command = { command: "apizr.openSource", title: "Open saved source", arguments: [root, location] }; }
        if (!children && value !== undefined) { this.description = String(token ?? (typeof value === "string" ? value : stringify(value))).slice(0, 180); }
    }
}
export class EvidenceTree implements vscode.TreeDataProvider<EvidenceItem> {
    private readonly changes = new vscode.EventEmitter<EvidenceItem | undefined>();
    readonly onDidChangeTreeData = this.changes.event;
    items: EvidenceItem[] = [];
    getTreeItem(item: EvidenceItem): vscode.TreeItem { return item; }
    getChildren(item?: EvidenceItem): EvidenceItem[] {
        if (!item) { return this.items; }
        if (!item.value || typeof item.value !== "object" || item.pointer.split("/").length > 16) { return []; }
        return Object.entries(item.value).slice(0, 1000).map(([key, value]) => new EvidenceItem(key, value, `${item.pointer}/${key.replace(/~/g, "~0").replace(/\//g, "~1")}`, item.root, item.locations, numberToken(item.value as object, key)));
    }
    changed(): void { this.changes.fire(undefined); }
    dispose(): void { this.changes.dispose(); }
}
export class Documents implements vscode.TextDocumentContentProvider {
    private readonly entries = new Map<string, string>();
    private sequence = 0;
    provideTextDocumentContent(uri: vscode.Uri): string { return this.entries.get(uri.toString()) ?? "Result expired; rerun the explicit Apizr command."; }
    async show(kind: string, value: Json): Promise<vscode.Uri> {
        const uri = vscode.Uri.parse(`apizr-result:/${kind}-${++this.sequence}.json`);
        const text = stringify(value, 2);
        if (Buffer.byteLength(text) > 16777216) { throw new EngineError("response_too_large", "The rendered result exceeds the editor limit."); }
        while (this.entries.size >= 3) { this.entries.delete(this.entries.keys().next().value!); }
        this.entries.set(uri.toString(), text);
        const document = await vscode.workspace.openTextDocument(uri);
        await vscode.window.showTextDocument(document, { preview: true, viewColumn: vscode.ViewColumn.Beside });
        return uri;
    }
    clear(): void { this.entries.clear(); }
}
export function locations(value: { [key: string]: Json }): Map<string, Location> {
    const result = new Map<string, Location>();
    if (Array.isArray(value.locations)) {
        for (const item of value.locations) {
            if (object(item) && typeof item.evidence === "string" && object(item.location) && typeof item.location.source === "string" && Number.isInteger(item.location.line) && Number.isInteger(item.location.column)) { result.set(item.evidence, item.location as unknown as Location); }
        }
    }
    return result;
}
export function relativeSource(root: string, filename: string): string {
    const source = path.relative(root, filename);
    if (!source || source === ".." || source.startsWith(`..${path.sep}`) || path.isAbsolute(source)) { throw new EngineError("source_outside_scope", "Select a saved source inside the configured project root."); }
    return source.split(path.sep).join("/");
}
export async function navigate(root: string, location: Location): Promise<void> {
    if (!location.source || path.isAbsolute(location.source) || location.source.split(/[\\/]/).some(p => p === ".." || p === "." || p === "") || /[\\:\x00-\x1f]/.test(location.source) || !Number.isInteger(location.line) || location.line < 1 || !Number.isInteger(location.column) || location.column < 0) { throw new EngineError("invalid_location", "The recorded source location is unavailable."); }
    const realRoot = await fs.realpath(root);
    const realSource = await fs.realpath(path.join(root, location.source));
    relativeSource(realRoot, realSource);
    const uri = vscode.Uri.file(realSource);
    if (path.extname(realSource) === ".ipynb" && location.cell_index === undefined) {
        await vscode.window.showNotebookDocument(await vscode.workspace.openNotebookDocument(uri));
        return;
    }
    let document: vscode.TextDocument;
    if (location.cell_index !== undefined) {
        const notebook = await vscode.workspace.openNotebookDocument(uri);
        if (!Number.isInteger(location.cell_index) || location.cell_index < 0 || location.cell_index >= notebook.cellCount || !Number.isInteger(location.cell_line) || location.cell_line! < 1) { throw new EngineError("invalid_location", "The recorded notebook cell is unavailable in the current file."); }
        await vscode.window.showNotebookDocument(notebook, { selections: [new vscode.NotebookRange(location.cell_index, location.cell_index + 1)] });
        document = notebook.cellAt(location.cell_index).document;
    } else { document = await vscode.workspace.openTextDocument(uri); }
    const line = Math.min((location.cell_line ?? location.line) - 1, document.lineCount - 1);
    const text = document.lineAt(line).text;
    const column = Math.min(Buffer.from(text).subarray(0, location.column).toString("utf8").length, text.length);
    const position = new vscode.Position(line, column);
    await vscode.window.showTextDocument(document, { selection: new vscode.Range(position, position) });
}
