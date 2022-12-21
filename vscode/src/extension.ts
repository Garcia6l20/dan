// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import * as commands from './pymake/commands';
import * as debuggerModule from './pymake/debugger';
import { Target } from './pymake/targets';
import { StatusBar } from './status';


export class PyMake implements vscode.Disposable {
	config: vscode.WorkspaceConfiguration;
	projectRoot: string;
	toolchains: string[];
	targets: Target[];
	activeTarget: Target | null = null;
	activeTargetChanged = new vscode.EventEmitter<Target>();

	private readonly _statusBar = new StatusBar(this);

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

	getConfig<T>(name: string) : T|undefined {
		return this.config.get<T>(name);
	}

	get buildPath() : string {
		return this.projectRoot + '/' + this.getConfig<string>('buildFolder') ?? 'build';
	}

	/**
	 * Create the instance
	 */
	static async create(context: vscode.ExtensionContext) {
		gExtension = new PyMake(context);

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

	async promptTarget(executable: boolean = false) {
		let targets = this.targets = await commands.getTargets(this);
		if (executable) {
			targets = targets.filter(t => t.executable === true);
		}
		let target = await vscode.window.showQuickPick(targets.map(t => t.name));
		if (target) {
			this.activeTarget = targets.filter(t => t.name === target)[0];
			this.activeTargetChanged.fire(this.activeTarget);
		}
		return this.activeTarget;
	}

	async registerCommands() {
		const register = (id: string, callback: (...args: any[]) => any, thisArg?: any) => {
			this.extensionContext.subscriptions.push(
				vscode.commands.registerCommand(`pymake.${id}`, callback, thisArg)
			);
		};

		register('scanToolchains', async () => commands.scanToolchains(this));
		register('configure', async () => commands.configure(this));
		register('build', async () => commands.build(this));
		register('clean', async () => commands.clean(this));
		register('run', async () => {
			if (!this.activeTarget || !this.activeTarget.executable) {
				await this.promptTarget(true);
			}
			if (this.activeTarget && this.activeTarget.executable) {
				await commands.run(this);
			}
		});
		register('debug', async () => {
			if (!this.activeTarget || !this.activeTarget.executable) {
				await this.promptTarget(true);
			}
			if (this.activeTarget && this.activeTarget.executable) {
				await commands.build(this);
				await debuggerModule.debug(this.getConfig<string>('debuggerPath') ?? 'gdb', this.activeTarget);
			}
		});
		register('setTarget', async () => this.promptTarget());
	}

	async onLoaded() {
		this.toolchains = await commands.getToolchains();
		this.targets = await commands.getTargets(this);

		vscode.commands.executeCommand("setContext", "inPyMakeProject", true);
	}
};


export let gExtension: PyMake | null = null;

// This method is called when your extension is activated
// Your extension is activated the very first time the command is executed
export async function activate(context: vscode.ExtensionContext) {
	await PyMake.create(context);
}

// This method is called when your extension is deactivated
export async function deactivate() {
	await gExtension?.cleanup();
}
