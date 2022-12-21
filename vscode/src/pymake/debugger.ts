
// /**
//  * Basically the same interface as vscode.DebugConfiguration, but we want
//  * strong typing on the optional properties so we need to redefine it so
//  * it can inherit those properties.
//  */
// export interface VSCodeDebugConfiguration extends CppDebugConfiguration {
//     type: string;
//     name: string;
//     request: string;
//     program: string;
//     [key: string]: any;
// }

// /**
//  * interface that maps to cmake.debugConfig.
//  */
// export interface CppDebugConfiguration {
//     symbolSearchPath?: string;
//     additionalSOLibSearchPath?: string;
//     externalConsole?: boolean;
//     console?: ConsoleTypes;
//     logging?: DebuggerLogging;
//     visualizerFile?: string;
//     args?: string[];
//     cwd?: string;
//     environment?: proc.DebuggerEnvironmentVariable[];
//     MIMode?: MIModes;
//     miDebuggerPath?: string;
//     stopAtEntry?: boolean;
//     setupCommands?: SetupCommand[];
//     customLaunchSetupCommands?: SetupCommand[];
//     launchCompleteCommand?: string;
//     dumpPath?: string;
//     coreDumpPath?: string;
// }

// export interface DebuggerLogging {
//     exceptions?: boolean;
//     moduleLoad?: boolean;
//     programOutput?: boolean;
//     engineLogging?: boolean;
//     trace?: boolean;
//     traceResponse?: boolean;
// }

// export interface SetupCommand {
//     text?: string;
//     description?: string;
//     ignoreFailures?: boolean;
// }

// export enum MIModes {
//     lldb = 'lldb',
//     gdb = 'gdb',
// }

// export enum ConsoleTypes {
//     internalConsole = 'internalConsole',
//     integratedTerminal = 'integratedTerminal',
//     externalTerminal = 'externalTerminal',
//     newExternalWindow = 'newExternalWindow'
// }

// async function createGDBDebugConfiguration(debuggerPath: string, target: ExecutableTarget): Promise<VSCodeDebugConfiguration> {
//     if (!await checkDebugger(debuggerPath)) {
//         debuggerPath = 'gdb';
//         if (!await checkDebugger(debuggerPath)) {
//             throw new Error(localize('gdb.not.found', 'Unable to find GDB in default search path and {0}.', debuggerPath));
//         }
//     }

//     return {
//         type: 'cppdbg',
//         name: `Debug ${target.name}`,
//         request: 'launch',
//         cwd: path.dirname(target.path),
//         args: [],
//         MIMode: MIModes.gdb,
//         miDebuggerPath: debuggerPath,
//         setupCommands: [
//             {
//                 description: localize('enable.pretty.printing', 'Enable pretty-printing for gdb'),
//                 text: '-enable-pretty-printing',
//                 ignoreFailures: true
//             }
//         ],
//         program: target.path
//     };
// }

// async function createLLDBDebugConfiguration(debuggerPath: string, target: ExecutableTarget): Promise<VSCodeDebugConfiguration> {
//     if (!await checkDebugger(debuggerPath)) {
//         throw new Error(localize('gdb.not.found', 'Unable to find GDB in default search path and {0}.', debuggerPath));
//     }

//     return {
//         type: 'cppdbg',
//         name: `Debug ${target.name}`,
//         request: 'launch',
//         cwd: path.dirname(target.path),
//         args: [],
//         MIMode: MIModes.lldb,
//         miDebuggerPath: debuggerPath,
//         program: target.path
//     };
// }

// function createMsvcDebugConfiguration(target: ExecutableTarget): VSCodeDebugConfiguration {
//     return {
//         type: 'cppvsdbg',
//         name: `Debug ${target.name}`,
//         request: 'launch',
//         cwd: path.dirname(target.path),
//         args: [],
//         program: target.path
//     };
// }