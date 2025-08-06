import * as path from 'path';
import { workspace, ExtensionContext } from 'vscode';
import { LanguageClient, TransportKind } from 'vscode-languageclient/node';

let client: LanguageClient;

export function activate(context: ExtensionContext) {
  
  const serverModule = context.asAbsolutePath(
    path.join('server', 'out', 'server.js')
  );

  
  const debugOptions = { execArgv: ['--nolazy', '--inspect=6009'] };

  
  client = new LanguageClient(
    'spoonAuditLanguageServer',
    'Spoon Audit Language Server',
    {
      run:   { module: serverModule, transport: TransportKind.ipc },
      debug: { module: serverModule, transport: TransportKind.ipc, options: debugOptions }
    },
    {
      documentSelector: [{ scheme: 'file', language: 'solidity' }],
      synchronize: {
        fileEvents: workspace.createFileSystemWatcher('**/.spoon-audit-config.json')
      }
    }
  );

 
  client.start();
  context.subscriptions.push(client);
}

export function deactivate(): Thenable<void> | undefined {
  if (!client) {
    return undefined;
  }
  return client.stop();
}
