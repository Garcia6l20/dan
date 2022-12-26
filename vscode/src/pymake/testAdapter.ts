import * as vscode from "vscode";
import * as commands from "./commands";
import {
    RetireEvent,
    TestAdapter,
    TestEvent,
    TestLoadFinishedEvent,
    TestLoadStartedEvent,
    TestRunFinishedEvent,
    TestRunStartedEvent,
    TestSuiteEvent,
    TestSuiteInfo,
    TestInfo
} from "vscode-test-adapter-api";
import { Log } from "vscode-test-adapter-util";
import { PyMake } from "../extension";


export class PyMakeTestAdapter implements TestAdapter {
    private disposables: { dispose(): void }[] = [];

    private readonly testsEmitter = new vscode.EventEmitter<
        TestLoadStartedEvent | TestLoadFinishedEvent
    >();
    private readonly testStatesEmitter = new vscode.EventEmitter<
        TestRunStartedEvent | TestRunFinishedEvent | TestSuiteEvent | TestEvent
    >();

    constructor(
        private readonly ext: PyMake,
        private readonly log: Log
    ) {
        this.log.info('Initializing PyMake test adapter');

        this.disposables.push(
            this.testsEmitter,
            this.testStatesEmitter
        );
    }
    dispose() {
        for (const disposable of this.disposables) {
            disposable.dispose();
        }
        this.disposables = [];
    }

    get workspaceFolder() {
        return this.ext.workspaceFolder;
    }
    async load(): Promise<void> {
        this.log.info('Loading PyMake tests');
        this.testsEmitter.fire(<TestLoadStartedEvent>{ type: 'started' });

        try {
            const root: TestSuiteInfo = await commands.getTestSuites(this.ext);
            this.testsEmitter.fire(<TestLoadFinishedEvent>{
                type: 'finished',
                suite: root,
            });
        } catch (e: any) {
            this.testsEmitter.fire(<TestLoadFinishedEvent>{
                type: 'finished',
                errorMessage: e.toString(),
            });
        }
    }
    run(tests: string[]): Promise<void> {
        throw new Error("Method not implemented.");
    }
    debug?(tests: string[]): Promise<void> {
        throw new Error("Method not implemented.");
    }
    cancel(): void {
        throw new Error("Method not implemented.");
    }
    get tests(): vscode.Event<TestLoadStartedEvent | TestLoadFinishedEvent> {
        return this.testsEmitter.event;
    }
    get testStates(): vscode.Event<TestRunStartedEvent | TestRunFinishedEvent | TestSuiteEvent | TestEvent> {
        return this.testStatesEmitter.event;
    }
    retire?: vscode.Event<RetireEvent> | undefined;
    autorun?: vscode.Event<void> | undefined;
};
