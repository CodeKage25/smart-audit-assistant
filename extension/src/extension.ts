import * as vscode from 'vscode';
import { exec } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

interface AuditFinding {
  tool?: string;
  severity: string;
  title: string;
  description?: string;
  location: string;
  confidence?: number;
  reasoning?: string;
  suggested_fix?: string;
}

interface AuditReport {
  static: AuditFinding[];
  ai: AuditFinding[];
}

export function activate(context: vscode.ExtensionContext) {
  const diagnosticCollection = vscode.languages.createDiagnosticCollection('spoon-audit');
  const outputChannel = vscode.window.createOutputChannel('Spoon Audit');
  
  context.subscriptions.push(diagnosticCollection, outputChannel);

  // Status bar item
  const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.command = 'spoon-audit.runScan';
  statusBarItem.text = '🛡️ Scan Contract';
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Auto-scan on save
  const autoScanOnSave = vscode.workspace.onDidSaveTextDocument((document) => {
    if (document.languageId === 'solidity') {
      const config = vscode.workspace.getConfiguration('spoon-audit');
      if (config.get('autoScanOnSave', true)) {
        runScanCommand(document.uri.fsPath, false);
      }
    }
  });
  context.subscriptions.push(autoScanOnSave);

  // Commands
  const scanCommand = vscode.commands.registerCommand('spoon-audit.runScan', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return vscode.window.showErrorMessage('No active editor');
    }

    const fileUri = editor.document.uri;
    if (fileUri.scheme !== 'file' || !fileUri.fsPath.endsWith('.sol')) {
      return vscode.window.showErrorMessage('Open a Solidity (.sol) file first');
    }

    await runScanCommand(fileUri.fsPath, true);
  });

  const scanWithAICommand = vscode.commands.registerCommand('spoon-audit.runScanWithAI', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      return vscode.window.showErrorMessage('No active editor');
    }

    const fileUri = editor.document.uri;
    if (fileUri.scheme !== 'file' || !fileUri.fsPath.endsWith('.sol')) {
      return vscode.window.showErrorMessage('Open a Solidity (.sol) file first');
    }

    await runScanCommand(fileUri.fsPath, true, true);
  });

  const clearDiagnosticsCommand = vscode.commands.registerCommand('spoon-audit.clearDiagnostics', () => {
    diagnosticCollection.clear();
    vscode.window.showInformationMessage('Spoon Audit diagnostics cleared');
  });

  const showReportCommand = vscode.commands.registerCommand('spoon-audit.showReport', async () => {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      return vscode.window.showErrorMessage('No workspace folder open');
    }

    const reportPath = path.join(workspaceFolder.uri.fsPath, 'last_report.json');
    if (!fs.existsSync(reportPath)) {
      return vscode.window.showErrorMessage('No scan report found. Run a scan first.');
    }

    try {
      const reportContent = fs.readFileSync(reportPath, 'utf8');
      const report = JSON.parse(reportContent);
      await showReportWebview(context, report);
    } catch (error) {
      vscode.window.showErrorMessage('Failed to read scan report');
    }
  });

  context.subscriptions.push(scanCommand, scanWithAICommand, clearDiagnosticsCommand, showReportCommand);

  // Hover provider for diagnostics
  const hoverProvider = vscode.languages.registerHoverProvider('solidity', {
    provideHover(document, position) {
      const diagnostics = diagnosticCollection.get(document.uri);
      if (!diagnostics) return null;

      const diagnostic = diagnostics.find(d => d.range.contains(position));
      if (!diagnostic) return null;

      const finding = (diagnostic as any).finding as AuditFinding;
      if (!finding) return null;

      const markdown = new vscode.MarkdownString();
      markdown.appendMarkdown(`**${finding.title}**\n\n`);
      
      if (finding.description) {
        markdown.appendMarkdown(`${finding.description}\n\n`);
      }
      
      if (finding.reasoning) {
        markdown.appendMarkdown(`**Reasoning:** ${finding.reasoning}\n\n`);
      }
      
      if (finding.suggested_fix) {
        markdown.appendMarkdown(`**Suggested Fix:** ${finding.suggested_fix}\n\n`);
      }
      
      if (finding.confidence !== undefined) {
        markdown.appendMarkdown(`**Confidence:** ${(finding.confidence * 100).toFixed(0)}%`);
      }

      return new vscode.Hover(markdown);
    }
  });

  context.subscriptions.push(hoverProvider);


const codeActionProvider: vscode.Disposable = vscode.languages.registerCodeActionsProvider(
  'solidity',
  {
    provideCodeActions(
      document: vscode.TextDocument,
      range: vscode.Range | vscode.Selection,
      context: vscode.CodeActionContext,
      token: vscode.CancellationToken
    ): vscode.ProviderResult<vscode.CodeAction[]> {
      const diagnostics = diagnosticCollection.get(document.uri);
      if (!diagnostics) return [];

      const actions: vscode.CodeAction[] = [];
      
      for (const diagnostic of diagnostics) {
        if (diagnostic.range.intersection(range)) {
          const finding = (diagnostic as any).finding as AuditFinding;
          if (finding?.suggested_fix) {
            const action = new vscode.CodeAction(
              `Apply fix: ${finding.title}`,
              vscode.CodeActionKind.QuickFix
            );
            action.diagnostics = [diagnostic];
            action.command = {
              command: 'spoon-audit.applyFix',
              title: 'Apply Fix',
              arguments: [document.uri, finding]
            };
            actions.push(action);
          }
        }
      }

      return actions;
    }
  }
);
  
  context.subscriptions.push(codeActionProvider);

  async function runScanCommand(filePath: string, showProgress: boolean, includeAI: boolean = false) {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(vscode.Uri.file(filePath));
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : path.dirname(filePath);
    const aiFlag = includeAI ? '' : '--no-ai';
    const cliCmd = `spoon-audit scan "${filePath}" ${aiFlag} --output-format json`;

    const runScan = () => {
      return new Promise<void>((resolve) => {
        outputChannel.appendLine(`Running: ${cliCmd}`);
        
        exec(cliCmd, { cwd }, (err, stdout, stderr) => {
          diagnosticCollection.clear();

          if (err) {
            outputChannel.appendLine(`Error: ${stderr || err.message}`);
            vscode.window.showErrorMessage(`Spoon Audit error: ${stderr || err.message}`);
            return resolve();
          }

          try {
            // Parse report from the last_report.json file
            const reportPath = path.join(cwd, 'last_report.json');
            if (fs.existsSync(reportPath)) {
              const reportContent = fs.readFileSync(reportPath, 'utf8');
              const report: AuditReport = JSON.parse(reportContent);
              
              const fileUri = vscode.Uri.file(filePath);
              const diagnostics: vscode.Diagnostic[] = [];

              // Process static findings
              for (const finding of report.static || []) {
                const diagnostic = createDiagnostic(finding, filePath);
                if (diagnostic) {
                  (diagnostic as any).finding = finding;
                  diagnostics.push(diagnostic);
                }
              }

              // Process AI findings
              for (const finding of report.ai || []) {
                const diagnostic = createDiagnostic(finding, filePath);
                if (diagnostic) {
                  (diagnostic as any).finding = finding;
                  diagnostics.push(diagnostic);
                }
              }

              diagnosticCollection.set(fileUri, diagnostics);
              
              const totalFindings = (report.static?.length || 0) + (report.ai?.length || 0);
              statusBarItem.text = totalFindings > 0 ? `🛡️ ${totalFindings} issues` : '🛡️ No issues';
              
              outputChannel.appendLine(`Scan complete: ${totalFindings} findings`);
            }
          } catch (e) {
            outputChannel.appendLine(`Failed to parse output: ${e}`);
            vscode.window.showErrorMessage(`Failed to parse spoon-audit output: ${e}`);
          }

          resolve();
        });
      });
    };

    if (showProgress) {
      await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: ` ${includeAI ? 'AI + Static' : 'Static'} Analysis: ${path.basename(filePath)}`,
        cancellable: false
      }, runScan);
    } else {
      await runScan();
    }
  }

  function createDiagnostic(finding: AuditFinding, filePath: string): vscode.Diagnostic | null {
    const [, lineStr] = finding.location.split(':');
    const lineNum = parseInt(lineStr, 10) - 1;
    
    if (isNaN(lineNum) || lineNum < 0) {
      return null;
    }

    const range = new vscode.Range(lineNum, 0, lineNum, Number.MAX_SAFE_INTEGER);
    const message = finding.tool 
      ? `${finding.tool}: ${finding.title}` 
      : finding.title;
    
    let severity: vscode.DiagnosticSeverity;
    switch (finding.severity.toLowerCase()) {
      case 'critical':
      case 'high':
        severity = vscode.DiagnosticSeverity.Error;
        break;
      case 'medium':
        severity = vscode.DiagnosticSeverity.Warning;
        break;
      case 'low':
      case 'info':
        severity = vscode.DiagnosticSeverity.Information;
        break;
      default:
        severity = vscode.DiagnosticSeverity.Warning;
    }

    const diagnostic = new vscode.Diagnostic(range, message, severity);
    diagnostic.source = 'spoon-audit';
    
    return diagnostic;
  }
}

async function showReportWebview(context: vscode.ExtensionContext, report: any) {
  const panel = vscode.window.createWebviewPanel(
    'spoonAuditReport',
    'Spoon Audit Report',
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true
    }
  );

  panel.webview.html = getWebviewContent(report);
}

function getWebviewContent(report: any): string {
  const staticFindings = report.static || [];
  const aiFindings = report.ai || [];
  
  return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spoon Audit Report</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
        }
        .header {
            border-bottom: 1px solid var(--vscode-panel-border);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        .section {
            margin-bottom: 30px;
        }
        .finding {
            background: var(--vscode-editor-background);
            border: 1px solid var(--vscode-panel-border);
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .severity {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .severity.critical { background: #dc3545; color: white; }
        .severity.high { background: #fd7e14; color: white; }
        .severity.medium { background: #ffc107; color: black; }
        .severity.low { background: #20c997; color: white; }
        .severity.info { background: #17a2b8; color: white; }
        .finding-title {
            font-size: 16px;
            font-weight: bold;
            margin: 10px 0;
        }
        .finding-details {
            margin-top: 10px;
        }
        .confidence {
            float: right;
            color: var(--vscode-descriptionForeground);
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ Spoon Audit Report</h1>
        <p><strong>Contract:</strong> ${report.path}</p>
        <p><strong>Scan Date:</strong> ${new Date(report.timestamp * 1000).toLocaleString()}</p>
        <p><strong>Total Findings:</strong> ${staticFindings.length + aiFindings.length}</p>
    </div>

    <div class="section">
        <h2>Static Analysis Findings (${staticFindings.length})</h2>
        ${staticFindings.map((finding: AuditFinding) => `
            <div class="finding">
                <span class="severity ${finding.severity}">${finding.severity}</span>
                <span class="confidence">${finding.tool}</span>
                <div class="finding-title">${finding.title}</div>
                <div class="finding-details">
                    <strong>Location:</strong> ${finding.location}<br>
                    ${finding.description ? `<strong>Description:</strong> ${finding.description}<br>` : ''}
                </div>
            </div>
        `).join('')}
    </div>

    <div class="section">
        <h2>AI Analysis Findings (${aiFindings.length})</h2>
        ${aiFindings.map((finding: AuditFinding) => `
            <div class="finding">
                <span class="severity ${finding.severity}">${finding.severity}</span>
                <span class="confidence">Confidence: ${finding.confidence ? Math.round(finding.confidence * 100) : 'N/A'}%</span>
                <div class="finding-title">${finding.title}</div>
                <div class="finding-details">
                    <strong>Location:</strong> ${finding.location}<br>
                    ${finding.description ? `<strong>Description:</strong> ${finding.description}<br>` : ''}
                    ${finding.reasoning ? `<strong>Reasoning:</strong> ${finding.reasoning}<br>` : ''}
                    ${finding.suggested_fix ? `<strong>Suggested Fix:</strong> ${finding.suggested_fix}<br>` : ''}
                </div>
            </div>
        `).join('')}
    </div>
</body>
</html>`;
}

export function deactivate() {}