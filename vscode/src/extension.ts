// The module 'vscode' contains the VS Code extensibility API
// Import the module and reference it with the alias vscode in your code below
import * as vscode from 'vscode';
import * as commands from './pymake/commands';
import * as debuggerModule from './pymake/debugger';
import * as path from 'path'
import { Target } from './pymake/targets';
import { StatusBar } from './status';
import { PyMakeTestAdapter } from './pymake/testAdapter';
import { TestHub, testExplorerExtensionId } from 'vscode-test-adapter-api';
import { Log, TestAdapterRegistrar } from 'vscode-test-adapter-util';
import { CppToolsApi, Version, getCppToolsApi } from 'vscode-cpptools';
import { ConfigurationProvider as CppToolsConfigurationProvider } from './cpptools';
import { existsSync } from 'fs';


class TargetPickItem {
	label: string;
	constructor(public readonly target: Target) {
		this.label = target.fullname;
	}
};

export class PyMake implements vscode.Disposable {
	config: vscode.WorkspaceConfiguration;
	workspaceFolder: vscode.WorkspaceFolder;
	projectRoot: string;
	toolchains: string[];
	targets: Target[];
	launchTarget: Target | null = null;
	launchTargetChanged = new vscode.EventEmitter<Target>();
	buildTargets: Target[] = [];
	buildTargetsChanged = new vscode.EventEmitter<Target[]>();
	tests: string[] = [];
	testsChanged = new vscode.EventEmitter<string[]>();

	private readonly _statusBar = new StatusBar(this);

	constructor(public readonly extensionContext: vscode.ExtensionContext) {
		this.config = vscode.workspace.getConfiguration("pymake");
		if (vscode.workspace.workspaceFolders) {
			this.workspaceFolder = vscode.workspace.workspaceFolders[0];
			this.projectRoot = this.workspaceFolder.uri.fsPath;
		} else {
			throw new Error('Cannot resolve project root');
		}
		this.toolchains = [];
		this.targets = [];
		vscode.workspace.onDidChangeConfiguration((e: vscode.ConfigurationChangeEvent) => {
			this.config = vscode.workspace.getConfiguration("pymake");
		});
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

	async promptTests() {
		let tests = this.tests = await commands.getTests(this);
		class TestPick {
			constructor(public label: string) { }
		};
		let pick = vscode.window.createQuickPick<TestPick>();
		pick.canSelectMany = true;
		pick.items = tests.map(t => new TestPick(t));
		let promise = new Promise<string[]>((res, rej) => {
			pick.show();
			pick.onDidAccept(() => {
				pick.hide();
			});
			pick.onDidHide(() => {
				res(pick.selectedItems.map(pt => pt.label));
			});
		});
		tests = await promise;
		pick.dispose();
		this.tests = tests;
		this.testsChanged.fire(this.tests);
		return this.tests;
	}

	configured() {
		return existsSync(path.join(this.buildPath, 'pymake.config.yaml'));
	}

	async ensureConfigured() {
		if (!this.configured()) {
			await commands.configure(this);
		}
	}

	async registerCommands() {
		const register = (id: string, callback: (...args: any[]) => any, thisArg?: any) => {
			this.extensionContext.subscriptions.push(
				vscode.commands.registerCommand(`pymake.${id}`, callback, thisArg)
			);
		};

		register('scanToolchains', async () => commands.scanToolchains(this));
		register('configure', async () => commands.configure(this));
		register('build', async () => {
			await this.ensureConfigured();
			await commands.build(this, this.buildTargets);
		});
		register('debugBuild', async () => {
			await this.ensureConfigured();
			await commands.build(this, this.buildTargets, true);
		});
		register('clean', async () => {
			if (this.configured()) {
				await commands.clean(this);
			}
		});
		register('run', async () => {
			await this.ensureConfigured();
			if (!this.launchTarget || !this.launchTarget.executable) {
				await this.promptLaunchTarget();
			}
			if (this.launchTarget && this.launchTarget.executable) {
				await commands.run(this);
			}
		});
		register('debug', async () => {
			await this.ensureConfigured();
			if (!this.launchTarget || !this.launchTarget.executable) {
				await this.promptLaunchTarget();
			}
			if (this.launchTarget && this.launchTarget.executable) {
				await commands.build(this);
				await debuggerModule.debug(this.launchTarget);
			}
		});
		register('test', async () => {
			await this.ensureConfigured();
			await commands.test(this);
		});
		register('selectLaunchTarget', async () => this.promptLaunchTarget());
		register('selectBuildTargets', async () => this.promptBuildTargets());
		register('selectTestTargets', async () => this.promptTests());
	}

	async initTestExplorer() {
		// setup Test Explorer
		const testExplorerExtension = vscode.extensions.getExtension<TestHub>(
			testExplorerExtensionId
		);

		if (testExplorerExtension) {
			const testHub = testExplorerExtension.exports;
			const log = new Log('PyMakeTestExplorer', this.workspaceFolder, 'PyMake Explorer Log');
			this.extensionContext.subscriptions.push(log);

			// this will register a CmakeAdapter for each WorkspaceFolder
			this.extensionContext.subscriptions.push(
				new TestAdapterRegistrar(
					testHub,
					(workspaceFolder) => new PyMakeTestAdapter(this, log),
					log
				)
			);
		}
	}

	_cppToolsApi: CppToolsApi|undefined = undefined;
	_cppToolsProvider: CppToolsConfigurationProvider|undefined = undefined;

	async initCppTools() {
		this._cppToolsApi = await getCppToolsApi(Version.v2);
		this._cppToolsProvider = new CppToolsConfigurationProvider(this);
		if (this._cppToolsApi) {
			if (this._cppToolsApi.notifyReady) {
				// Inform cpptools that a custom config provider will be able to service the current workspace.
				this._cppToolsApi.registerCustomConfigurationProvider(this._cppToolsProvider);

				// Do any required setup that the provider needs.
				// await this._cppToolsProvider.refresh();

				// Notify cpptools that the provider is ready to provide IntelliSense configurations.
				this._cppToolsApi.notifyReady(this._cppToolsProvider);
			} else {
				// Running on a version of cpptools that doesn't support v2 yet.
				
				// Do any required setup that the provider needs.
				// await this._cppToolsProvider.refresh();

				// Inform cpptools that a custom config provider will be able to service the current workspace.
				this._cppToolsApi.registerCustomConfigurationProvider(this._cppToolsProvider);
				this._cppToolsApi.didChangeCustomConfiguration(this._cppToolsProvider);
			}
		}

	}

	async onLoaded() {
		this.toolchains = await commands.getToolchains(this);
		await this.ensureConfigured();
		this.targets = await commands.getTargets(this);

		vscode.commands.executeCommand("setContext", "inPyMakeProject", true);

		await this.initCppTools();
		await this.initTestExplorer();
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
