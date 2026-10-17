import * as vscode from "vscode";

/** Resolve editor/menu context to its saved file, including notebook cell URIs. */
export function sourceUri(context?: unknown): vscode.Uri | undefined {
    const menu = context as { notebookEditor?: vscode.NotebookEditor; notebook?: vscode.NotebookDocument } | undefined;
    const explicit = context instanceof vscode.Uri ? context : menu?.notebookEditor?.notebook.uri ?? menu?.notebook?.uri;
    const selected = explicit ?? vscode.window.activeTextEditor?.document.uri;
    if (selected?.scheme === "vscode-notebook-cell") {
        return vscode.workspace.notebookDocuments.find(notebook => notebook.getCells().some(cell => cell.document.uri.toString() === selected.toString()))?.uri;
    }
    if (explicit) { return selected?.scheme === "file" ? selected : undefined; }
    if (selected?.scheme === "file") { return selected; }
    if (selected?.scheme === "untitled") { return undefined; }
    return vscode.window.activeNotebookEditor?.notebook.uri ?? selected;
}

export function inspectionLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    if (!vscode.workspace.isTrusted || !vscode.workspace.getConfiguration("apizr", document.uri).get("codeLens", true)) { return []; }
    const range = new vscode.Range(0, 0, 0, 0);
    return [
        new vscode.CodeLens(range, { title: "Apizr: Inspect saved file", command: "apizr.inspect", arguments: [document.uri] }),
        new vscode.CodeLens(range, { title: "Experiment dashboard", command: "apizr.openDashboard" }),
    ];
}
