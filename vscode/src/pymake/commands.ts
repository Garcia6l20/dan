import * as vscode from "vscode";
import * as cp from "child_process";
import { PyMakeExtension } from "../extension";

export function execStream(
    command: string[],
    options: cp.SpawnOptions
) {
    const spawned = cp.spawn(command[0], command.slice(1), options);
    return {
        onLine(fn: (line: string, isError: boolean) => void) {
            spawned.stdout?.on("data", (msg: Buffer) => fn(msg.toString(), false));
            spawned.stderr?.on("data", (msg: Buffer) => fn(msg.toString(), true));
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
export function getOutputChannel(): vscode.OutputChannel {
    if (!_channel) {
        _channel = vscode.window.createOutputChannel("PyMake");
    }
    return _channel;
}

function exec(command: string,
    parameters: string[] = [],
    title: string | null = null,
    cancellable: boolean = true,
    cwd: string | undefined = undefined) {
    let stream = execStream(['python', '-m', 'pymake', command, ...parameters], { cwd: cwd });
    title = title ?? `Executing ${command} ${parameters.join(' ')}`;
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
            stream.onLine((msg, isError) => {
                const match = /(.+):\s+(\d+)%\|/g.exec(msg);
                if (match) {
                    const percentage = parseInt(match[2]);
                    const increment = percentage - oldPercentage;
                    oldPercentage = percentage;
                    if (increment > 0) {
                        progress.report({ increment, message: match[1] });
                    }
                } else {
                    getOutputChannel().append(msg);
                }
                getOutputChannel().show();
            });
            await stream.finishP();
        }
    );

}

export async function scanToolchains(ext: PyMakeExtension) {
    let args = [];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return exec('scan-toolchains');
}


export async function configure(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return exec('configure', args, null, true, ext.projectRoot);
}

export async function build(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return exec('build', args, null, true, ext.projectRoot);
}

export async function clean(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return exec('clean', args, null, true, ext.projectRoot);
}
