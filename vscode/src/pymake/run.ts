import * as vscode from "vscode";
import * as cp from "child_process";

export function streamExec(
    command: string[],
    options: cp.SpawnOptions = {}
) {
    const spawned = cp.spawn(command[0], command.slice(1), options);
    return {
        onLine(fn: (line: Buffer, isError: boolean) => void) {
            spawned.stdout?.on("data", (msg: Buffer) => fn(msg, false));
            spawned.stderr?.on("data", (msg: Buffer) => fn(msg, true));
        },
        kill(signal?: NodeJS.Signals) {
            spawned.kill(signal || "SIGKILL");
        },
        finishP() {
            return new Promise<number>(res => {
                spawned.on("exit", code => res(code ? code : 0));
            });
        }
    };
}

let _channel: vscode.OutputChannel;
function getOutputChannel(): vscode.OutputChannel {
    if (!_channel) {
        _channel = vscode.window.createOutputChannel("PyMake");
    }
    return _channel;
}

export function channelExec(command: string,
    parameters: string[] = [],
    title: string | null = null,
    cancellable: boolean = true,
    cwd: string | undefined = undefined) {
    let stream = streamExec(['python', '-m', 'pymake', command, ...parameters], { cwd: cwd });
    title = title ?? `Executing ${command} ${parameters.join(' ')}`;
    const channel = getOutputChannel();
    channel.clear();
    channel.show();
    return vscode.window.withProgress(
        {
            title: title,
            location: vscode.ProgressLocation.Notification,
            cancellable: cancellable,
        },
        async (progress, token) => {
            token.onCancellationRequested(() => stream.kill());
            let oldPercentage = 0;
            progress.report({ message: 'command', increment: 0 });
            stream.onLine((msg: Buffer, isError) => {
                const line = msg.toString().trim();
                if (line.length === 0) {
                    return;
                }
                const match = /(.+):\s+(\d+)%\|/g.exec(line);
                if (match) {
                    const percentage = parseInt(match[2]);
                    const increment = percentage - oldPercentage;
                    oldPercentage = percentage;
                    if (increment > 0) {
                        progress.report({ increment: increment, message: match[1] });
                    }
                } else {
                    channel.appendLine(line);
                }
            });
            progress.report({ increment: 100 - oldPercentage, message: 'done' });
            await stream.finishP();
            channel.appendLine(`${command} done`);
        }
    );
}

function getTerminal(): vscode.Terminal {
    let terminal = vscode.window.terminals.find(t => t.name === 'PyMake') ?? null;
    if (!terminal) {
        terminal = vscode.window.createTerminal("PyMake");
    }
    terminal.show();
    return terminal;
}


export function termExec(command: string,
    parameters: string[] = [],
    title: string | null = null,
    cancellable: boolean = true,
    cwd: string | undefined = undefined) {
    let term = getTerminal();
    term.show();
    let args = ['python', '-m', 'pymake', command, ...parameters];
    if (cwd) {
        args.unshift('cd', cwd, '&&');
    }
    term.sendText(args.join(' '));
}
