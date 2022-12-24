// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import * as commands from './pymake/commands';
import * as debuggerModule from './pymake/debugger';
import { Target } from './pymake/targets';
import { StatusBar } from './status';


class TargetPickItem {
	label: string;
	constructor(public readonly target: Target) {
		this.label = target.fullname;
	}
};

export class PyMake implements vscode.Disposable {
	config: vscode.WorkspaceConfiguration;
	projectRoot: string;
	toolchains: string[];
	targets: Target[];
	launchTarget: Target | null = null;
	launchTargetChanged = new vscode.EventEmitter<Target>();
	buildTargets: Target[] = [];
	buildTargetsChanged = new vscode.EventEmitter<Target[]>();

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

	getConfig<T>(name: string): T | undefined {
		return this.config.get<T>(name);
	}

	get buildPath(): string {
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

	async promptLaunchTarget() {
		let targets = this.targets = await commands.getTargets(this);
		targets = targets.filter(t => t.executable === true);
		targets.sort((l, r) => l.fullname < r.fullname ? -1 : 1);
		let target = await vscode.window.showQuickPick(targets.map(t => t.fullname));
		if (target) {
			this.launchTarget = targets.filter(t => t.fullname === target)[0];
			this.launchTargetChanged.fire(this.launchTarget);
		}
		return this.launchTarget;
	}

	async promptBuildTargets() {
		let targets = this.targets = await commands.getTargets(this);
		targets.sort((l, r) => l.fullname < r.fullname ? -1 : 1);
		let pick = vscode.window.createQuickPick<TargetPickItem>();
		pick.canSelectMany = true;
		pick.items = targets.map(t => new TargetPickItem(t));
		let promise = new Promise<Target[]>((res, rej) => {
			pick.show();
			pick.onDidAccept(() => {
				pick.hide();
			});
			pick.onDidHide(() => {
				res(pick.selectedItems.map(pt => pt.target));
			});
		});
		targets = await promise;
		pick.dispose();
		this.buildTargets = targets;
		this.buildTargetsChanged.fire(this.buildTargets);
		return this.buildTargets;
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
			if (!this.launchTarget || !this.launchTarget.executable) {
				await this.promptLaunchTarget();
			}
			if (this.launchTarget && this.launchTarget.executable) {
				await commands.run(this);
			}
		});
		register('debug', async () => {
			if (!this.launchTarget || !this.launchTarget.executable) {
				await this.promptLaunchTarget();
			}
			if (this.launchTarget && this.launchTarget.executable) {
				await commands.build(this);
				await debuggerModule.debug(this.getConfig<string>('debuggerPath') ?? 'gdb', this.launchTarget);
			}
		});
		register('selectLaunchTarget', async () => this.promptLaunchTarget());
		register('selectBuildTargets', async () => this.promptBuildTargets());
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
