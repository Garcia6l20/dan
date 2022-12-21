// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import * as commands from './pymake/commands';
import { Target } from './pymake/targets';
import { StatusBar } from './status';


export class PyMakeExtension implements vscode.Disposable {
	config: vscode.WorkspaceConfiguration;
	projectRoot: string;
	toolchains: string[];
	targets: Target[];

	private readonly _statusBar = new StatusBar();

	constructor(public readonly extensionContext: vscode.ExtensionContext) {
		this.config = vscode.workspace.getConfiguration("pymake");
		if (vscode.workspace.workspaceFolders) {
			this.projectRoot = vscode.workspace.workspaceFolders[0].uri.fsPath;
		} else {
			throw new Error('Cannot resolve project root');
		}
		this.toolchains = [];
		this.targets = [];
	}

	getConfig<T>(name: string, defaultValue: T|undefined = undefined) : T|undefined {
		return this.config.get<T>(name) ?? defaultValue;
	}

	get buildPath() : string {
		return this.projectRoot + '/' + this.getConfig<string>('buildFolder', 'build');
	}

	/**
	 * Create the instance
	 */
	static async create(context: vscode.ExtensionContext) {
		gExtension = new PyMakeExtension(context);

		await gExtension.registerCommands();
		await gExtension.onLoaded();

		vscode.commands.executeCommand("setContext", "inMesonProject", true);
	}

	/**
	 * Dispose the instance
	 */
	dispose() {
		(async () => {
			this.cleanup();
		})();
	}

	async cleanup() {
	}

	async registerCommands() {
		const register = (id: string, callback: (...args: any[]) => any, thisArg?: any) => {
			this.extensionContext.subscriptions.push(
				vscode.commands.registerCommand(`pymake.${id}`, callback, thisArg)
			);
		};

		register('scanToolchains', async () => { await commands.scanToolchains(this); });
		register('configure', async () => { await commands.configure(this); });
		register('build', async () => { await commands.build(this); });
		register('clean', async () => { await commands.clean(this); });
		register('run', async () => { await commands.run(this); });
		register('debug', async () => { console.log('not implemented'); });
	}

	async onLoaded() {
		this.toolchains = await commands.getToolchains();
		this.targets = await commands.getTargets(this);

		vscode.commands.executeCommand("setContext", "inPyMakeProject", true);
	}
};


export let gExtension: PyMakeExtension | null = null;

// This method is called when your extension is activated
// Your extension is activated the very first time the command is executed
export async function activate(context: vscode.ExtensionContext) {
	await PyMakeExtension.create(context);
}

// This method is called when your extension is deactivated
export async function deactivate() {
	await gExtension?.cleanup();
}
