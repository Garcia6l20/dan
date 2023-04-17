import * as vscode from "vscode";
import * as path from 'path';
import * as commands from "./commands";
import * as run from "./run";
import * as debuggerModule from './debugger';
import {
    RetireEvent,
    TestAdapter,
    TestEvent,
    TestLoadFinishedEvent,
    TestLoadStartedEvent,
    TestRunFinishedEvent,
    TestRunStartedEvent,
    TestSuiteEvent,
    TestSuiteInfo as APITestSuiteInfo,
    TestInfo as APITestInfo,
} from "vscode-test-adapter-api";
import { promises as fsPromises } from 'fs';
import { Log } from "vscode-test-adapter-util";
import { PyMake } from "../extension";
import { Target } from "./targets";

export interface TestSuiteInfo extends APITestSuiteInfo {
    children: (TestSuiteInfo | TestInfo)[];
};

export interface TestInfo extends APITestInfo {
    /** The target ID associated to the test */
    target: string;

    /** The working directory of the test */
    workingDirectory: string;

    /** Arguments for the test */
    args?: string[];

    /** stdout file */
    out: string;
    /** stderr file */
    err: string;
};


export class PyMakeTestAdapter implements TestAdapter {
    private disposables: { dispose(): void }[] = [];
    private root: TestSuiteInfo | undefined = undefined;

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
            this.root = await commands.getTestSuites(this.ext);
            this.testsEmitter.fire(<TestLoadFinishedEvent>{
                type: 'finished',
                suite: this.root,
            });
        } catch (e: any) {
            this.testsEmitter.fire(<TestLoadFinishedEvent>{
                type: 'finished',
                errorMessage: e.toString(),
            });
        }
    }

    getInfo(test: string, suite: TestSuiteInfo | undefined = undefined): TestInfo | TestSuiteInfo | undefined {
        if (suite === undefined) {
            suite = this.root;
        }
        if (suite === undefined) {
            return undefined;
        }
        if (test === suite.id) {
            return suite;
        }
        for (const child of suite.children) {
            if (child.id === test) {
                return child;
            }
            if (child.type === 'suite') {
                const info = this.getInfo(test, child);
                if (info !== undefined) {
                    return info;
                }
            }
        }
        return undefined;
    }

    async runTest(test: TestInfo): Promise<void> {
        this.testStatesEmitter.fire(<TestEvent>{ type: "test", test: test.id, state: "running" });
        const stream = await run.streamExec(['python', '-m', 'pymake', 'test', '-q', this.ext.buildPath, test.id], { cwd: test.workingDirectory });
        let out: string = '';
        stream.onLine((line, isError) => {
            out += line;
        });
        const res = await stream.finished();
        let log: string = '';
        log += await fsPromises.readFile(path.join(test.out), 'utf-8');
        log += await fsPromises.readFile(path.join(test.err), 'utf-8');

        let event = <TestEvent>{
            type: "test",
            test: test.id,
            file: test.file,
            line: test.line,
            message: log,
        };
        if (res !== 0) {
            event.state = 'failed';
        } else {
            event.state = "passed";
        }
        this.testStatesEmitter.fire(event);
        this.testStatesEmitter.fire(<TestRunFinishedEvent>{ type: 'finished', testRunId: test.id });
    }

    async runSuite(suite: TestSuiteInfo): Promise<void> {
        let promises: Promise<void>[] = [];
        for (const test of suite.children) {
            if (test.type === 'test') {
                promises.push(this.runTest(test));
            } else {
                promises.push(this.runSuite(test));
            }
        }
        await Promise.all(promises);
    }

    getSuiteTargets(suite: TestSuiteInfo) {
        let targets: string[] = [];
        for (const info of suite.children) {
            if (info === undefined) {
                throw Error(`Cannot find infos of test ${test}`);
            }

            if (info.type === 'test') {
                targets.push(info.target);
            } else {
                for (const child of info.children) {
                    if (child.type === 'test') {
                        targets.push(child.target);
                    } else {
                        targets.push(...this.getSuiteTargets(child));
                    }
                }
            }
        }
        return targets;
    }

    getTargets(tests: string[]) {
        let targets: string[] = [];
        for (const test of tests) {
            const info = this.getInfo(test);
            if (info === undefined) {
                throw Error(`Cannot find infos of test ${test}`);
            }

            if (info.type === 'test') {
                targets.push(info.target);
            } else {
                targets.push(...this.getSuiteTargets(info));
            }
        }
        return targets;
    }

    async run(tests: string[]): Promise<void> {
        this.log.info(`Running tests ${JSON.stringify(tests)}`);

        this.testStatesEmitter.fire(<TestRunStartedEvent>{ type: 'started', tests });
        await commands.build(this.ext, this.getTargets(tests), false);
        let promises: Promise<void>[] = [];
        for (const test of tests) {
            const info = this.getInfo(test);
            if (info === undefined) {
                throw Error(`Cannot find infos of test ${test}`);
            }
            if (info.type === 'test') {
                promises.push(this.runTest(info));
            } else {
                promises.push(this.runSuite(info));
            }
        }
        await Promise.all(promises);
        this.testStatesEmitter.fire(<TestRunFinishedEvent>{ type: 'finished' });
    }
    async debug(tests: string[]): Promise<void> {
        for (const test of tests) {
            const info = this.getInfo(test);
            if (info === undefined) {
                throw Error(`Cannot find infos of test ${test}`);
            } else if (info.type === 'suite') {
                throw Error('Cannot debug a test suite');
            }
            let target: Target | undefined = undefined;
            for (const t of this.ext.targets) {
                if (t.fullname === info.target) {
                    target = t;
                    break;
                }
            }
            if (target === undefined) {
                throw Error(`Cannot find target ${info.target}`);
            }
            await commands.build(this.ext, [target]);
            await debuggerModule.debug(this.ext.getConfig<string>('debuggerPath') ?? 'gdb', target, info.args);
        }
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
