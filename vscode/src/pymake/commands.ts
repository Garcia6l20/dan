import * as vscode from "vscode";
import { channelExec, streamExec, termExec } from "./run";
import { PyMake } from "../extension";
import { Target } from "./targets";

export async function scanToolchains(ext: PyMake) {
    let args = [];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return channelExec('scan-toolchains');
}

const splitLines = (str: string) => str.split(/\r?\n/);

export async function getToolchains(): Promise<string[]> {
    let toolchains: string[] = [];
    let stream = streamExec(['pymake', 'list-toolchains']);
    let errors: string[] = [];
    stream.onLine((line, isError) => {
        if (!isError) {
            for (let item of splitLines(line)) {
                item = item.trim();
                if (item.length) {
                    toolchains.push(item);
                }
            }
        } else {
            errors.push(line.trim());
        }
    });
    await stream.finishP();
    if (errors.length) {
        await vscode.window.showErrorMessage('PyMake: Failed to get toolchains', { detail: errors.join('\n') });
        return [];
    } else {
        return toolchains;
    }
}

export async function getTargets(ext: PyMake): Promise<Target[]> {
    let stream = streamExec(['pymake', 'list', '-jq', ext.buildPath]);
    let errors: string[] = [];
    let data = '';
    stream.onLine((line, isError) => {
        if (!isError) {
            data += line;
        } else {
            errors.push(line.trim());
        }
    });
    await stream.finishP();
    if (errors.length) {
        await vscode.window.showErrorMessage('PyMake: Failed to get targets', { detail: errors.join('\n') });
        return [];
    } else {
        let targets : Target[] = [];
        let rawTargets = JSON.parse(data);
        for (let t of rawTargets) {
            targets.push(t as Target);
        }
        return targets;
    }
}

export async function configure(ext: PyMake) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return channelExec('configure', args, null, true, ext.projectRoot);
}

function baseArgs(ext: PyMake): string[] {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    if (ext.activeTarget) {
        args.push(ext.activeTarget);
    }
    return args;
}

export async function build(ext: PyMake) {
    return termExec('build', baseArgs(ext), null, true, ext.projectRoot);
}

export async function clean(ext: PyMake) {
    return termExec('clean', baseArgs(ext), null, true, ext.projectRoot);
}

export async function run(ext: PyMake) {
    return termExec('run', baseArgs(ext), null, true, ext.projectRoot);
}
