"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
function activate(context) {
    const diagnosticCollection = vscode.languages.createDiagnosticCollection('spoon-audit');
    context.subscriptions.push(diagnosticCollection);
    const disposable = vscode.commands.registerCommand('spoon-audit.runScan', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return vscode.window.showErrorMessage('No active editor');
        }
        const fileUri = editor.document.uri;
        if (fileUri.scheme !== 'file' || !fileUri.fsPath.endsWith('.sol')) {
            return vscode.window.showErrorMessage('Open a Solidity (.sol) file first');
        }
        const filePath = fileUri.fsPath;
        const workspaceFolder = vscode.workspace.getWorkspaceFolder(fileUri);
        const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);
        const cliCmd = `spoon-audit scan "${filePath}" --no-ai`;
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: `🛡️ Running Spoon Audit on ${path.basename(filePath)}`,
            cancellable: false
        }, (progress) => {
            return new Promise((resolve) => {
                (0, child_process_1.exec)(cliCmd, { cwd }, (err, stdout, stderr) => {
                    diagnosticCollection.clear();
                    if (err) {
                        vscode.window.showErrorMessage(`spoon-audit error: ${stderr || err.message}`);
                        return resolve();
                    }
                    try {
                        const report = JSON.parse(stdout);
                        const diagnostics = [];
                        for (const finding of report.static) {
                            const [, lineStr] = finding.location.split(':');
                            const lineNum = parseInt(lineStr, 10) - 1;
                            const range = new vscode.Range(lineNum, 0, lineNum, Number.MAX_SAFE_INTEGER);
                            const message = `${finding.tool}: ${finding.title}`;
                            const diag = new vscode.Diagnostic(range, message, vscode.DiagnosticSeverity.Warning);
                            diagnostics.push(diag);
                        }
                        diagnosticCollection.set(fileUri, diagnostics);
                    }
                    catch (e) {
                        vscode.window.showErrorMessage(`Failed to parse spoon-audit output: ${e}`);
                    }
                    resolve();
                });
            });
        });
    });
    context.subscriptions.push(disposable);
}
function deactivate() {
}
