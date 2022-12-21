import { Target } from "./targets";
import * as vscode from 'vscode';

export interface DebuggerEnvironmentVariable { name: string; value: string }

export interface DebuggerLogging {
    exceptions?: boolean;
    moduleLoad?: boolean;
    programOutput?: boolean;
    engineLogging?: boolean;
    trace?: boolean;
    traceResponse?: boolean;
}

export interface SetupCommand {
    text?: string;
    description?: string;
    ignoreFailures?: boolean;
}

export enum MIModes {
    lldb = 'lldb',
    gdb = 'gdb',
}

export enum ConsoleTypes {
    internalConsole = 'internalConsole',
    integratedTerminal = 'integratedTerminal',
    externalTerminal = 'externalTerminal',
    newExternalWindow = 'newExternalWindow'
}

/**
 * interface that maps to cmake.debugConfig.
 */
export interface CppDebugConfiguration {
    symbolSearchPath?: string;
    additionalSOLibSearchPath?: string;
    externalConsole?: boolean;
    console?: ConsoleTypes;
    logging?: DebuggerLogging;
    visualizerFile?: string;
    args?: string[];
    cwd?: string;
    environment?: DebuggerEnvironmentVariable[];
    MIMode?: MIModes;
    miDebuggerPath?: string;
    stopAtEntry?: boolean;
    setupCommands?: SetupCommand[];
    customLaunchSetupCommands?: SetupCommand[];
    launchCompleteCommand?: string;
    dumpPath?: string;
    coreDumpPath?: string;
}

/**
 * Basically the same interface as vscode.DebugConfiguration, but we want
 * strong typing on the optional properties so we need to redefine it so
 * it can inherit those properties.
 */
export interface VSCodeDebugConfiguration extends CppDebugConfiguration {
    type: string;
    name: string;
    request: string;
    program: string;
    [key: string]: any;
}

async function createGDBDebugConfiguration(debuggerPath: string, target: Target): Promise<VSCodeDebugConfiguration> {
    // if (!await checkDebugger(debuggerPath)) {
    //     debuggerPath = 'gdb';
    //     if (!await checkDebugger(debuggerPath)) {
    //         throw new Error(localize('gdb.not.found', 'Unable to find GDB in default search path and {0}.', debuggerPath));
    //     }
    // }

    return {
        type: 'cppdbg',
        name: `Debug ${target.name}`,
        request: 'launch',
        cwd: target.buildPath,
        args: [],
        MIMode: MIModes.gdb,
        miDebuggerPath: debuggerPath,
        setupCommands: [
            {
                description: 'Enable pretty-printing for gdb',
                text: '-enable-pretty-printing',
                ignoreFailures: true
            }
        ],
        program: target.output
    };
}

async function createLLDBDebugConfiguration(debuggerPath: string, target: Target): Promise<VSCodeDebugConfiguration> {
    // if (!await checkDebugger(debuggerPath)) {
    //     throw new Error(localize('gdb.not.found', 'Unable to find GDB in default search path and {0}.', debuggerPath));
    // }

    return {
        type: 'cppdbg',
        name: `Debug ${target.name}`,
        request: 'launch',
        cwd: target.buildPath,
        args: [],
        MIMode: MIModes.lldb,
        miDebuggerPath: debuggerPath,
        program: target.output
    };
}

function createMsvcDebugConfiguration(target: Target): VSCodeDebugConfiguration {
    return {
        type: 'cppvsdbg',
        name: `Debug ${target.name}`,
        request: 'launch',
        cwd: target.buildPath,
        args: [],
        program: target.output
    };
}

export async function debug(target: Target) {
    if (!target.executable) {
        throw Error(`Cannot debug "${target.name}, not an executable"`);
    }
    let debugConfig = await createGDBDebugConfiguration('gdb', target);
    await vscode.debug.startDebugging(undefined, debugConfig);
    return vscode.debug.activeDebugSession;
}
