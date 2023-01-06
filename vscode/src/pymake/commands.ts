import * as vscode from "vscode";
import { channelExec, streamExec, termExec } from "./run";
import { PyMake } from "../extension";
import { isTarget, Target } from "./targets";
import { TestSuiteInfo, TestInfo } from "./testAdapter";

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
    let stream = streamExec(['pymake', 'list-targets', '-js', '-q', ext.buildPath]);
    let data = '';
    stream.onLine((line, isError) => {
        data += line;
    });
    let rc = await stream.finishP();
    if (rc !== 0) {
        await vscode.window.showErrorMessage('PyMake: Failed to get targets', { modal: true, detail: data });
        return [];
    } else {
        let targets: Target[] = [];
        let rawTargets = JSON.parse(data);
        for (let t of rawTargets) {
            targets.push(t as Target);
        }
        return targets;
    }
}


export async function getTests(ext: PyMake): Promise<string[]> {
    let stream = streamExec(['pymake', 'list-tests', '-q', ext.buildPath]);
    let data = '';
    stream.onLine((line, isError) => {
        data += line;
    });
    let rc = await stream.finishP();
    if (rc !== 0) {
        await vscode.window.showErrorMessage('PyMake: Failed to get tests', { modal: true, detail: data });
        return [];
    } else {
        let tests: string[] = [];
        for (let t of splitLines(data)) {
            if (t.length > 0) {
                tests.push(t);
            }
        }
        return tests;
    }
}

export async function getTestSuites(ext: PyMake): Promise<TestSuiteInfo> {
    let stream = streamExec(['pymake', 'list-tests', '-js', '-q', ext.buildPath]);
    let data = '';
    stream.onLine((line, isError) => {
        data += line;
    });
    let rc = await stream.finishP();
    if (rc !== 0) {
        throw Error(`PyMake: Failed to get tests: ${data}`);
    } else {
        return JSON.parse(data) as TestSuiteInfo;
    }
}

export async function configure(ext: PyMake) {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    args.push('--toolchain');
    args.push(await vscode.window.showQuickPick(['default', ...ext.toolchains]) ?? 'default');
    return termExec('configure', args, null, true, ext.projectRoot);
}

function baseArgs(ext: PyMake): string[] {
    let args = [ext.buildPath];
    if (ext.getConfig<boolean>('verbose')) {
        args.push('-v');
    }
    const jobs = ext.getConfig<number>('jobs');
    if (jobs !== undefined) {
        args.push('-j', jobs.toString());
    }
    return args;
}

export async function build(ext: PyMake, targets: Target[] | string[] = [], terminal=true) {
    let args = baseArgs(ext);
    if (targets.length !== 0) {
        args.push(...targets.map((t) => {
            if (isTarget(t)) {
                return t.fullname;
            } else {
                return t;
            }
        }));
    }
    if (terminal) {
        termExec('build', args, null, true, ext.projectRoot);
    } else {
        await channelExec('build', args, null, true, ext.projectRoot);
    }
}

export async function clean(ext: PyMake) {
    return termExec('clean', [...baseArgs(ext), ...ext.buildTargets.map(t => t.fullname)], null, true, ext.projectRoot);
}

export async function run(ext: PyMake) {
    let args = baseArgs(ext);
    if (ext.launchTarget) {
        args.push(ext.launchTarget.fullname);
    }
    return termExec('run', args, null, true, ext.projectRoot);
}

export async function test(ext: PyMake) {
    let args = baseArgs(ext);
    args.push(...ext.tests);
    return termExec('test', args, null, true, ext.projectRoot);
}
