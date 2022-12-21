import * as vscode from "vscode";
import { channelExec, streamExec } from "./run";
import { PyMakeExtension } from "../extension";
import { Target } from "./targets";

export async function scanToolchains(ext: PyMakeExtension) {
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

export async function getTargets(ext: PyMakeExtension): Promise<Target[]> {
    let targets: Target[] = [];
    let stream = streamExec(['pymake', 'list', '-qt', ext.buildPath]);
    let errors: string[] = [];
    stream.onLine((line, isError) => {
        if (!isError) {
            for (let item of splitLines(line)) {
                item = item.trim();
                if (item.length) {
                    let [name, type] = item.split(' - ');
                    targets.push(new Target(name.trim(), type.trim()));
                }
            }
        } else {
            errors.push(line.trim());
        }
    });
    await stream.finishP();
    if (errors.length) {
        await vscode.window.showErrorMessage('PyMake: Failed to get targets', { detail: errors.join('\n') });
        return [];
    } else {
        return targets;
    }
}

export async function configure(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return channelExec('configure', args, null, true, ext.projectRoot);
}

export async function build(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return channelExec('build', args, null, true, ext.projectRoot);
}

export async function clean(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return channelExec('clean', args, null, true, ext.projectRoot);
}

export async function run(ext: PyMakeExtension) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    return channelExec('run', args, null, true, ext.projectRoot);
}
