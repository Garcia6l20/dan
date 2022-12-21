import * as vscode from 'vscode';
import { PyMake } from './extension';

// Button class
abstract class Button {
    readonly settingsName: string | null = null;
    protected readonly button: vscode.StatusBarItem;
    private _forceHidden: boolean = false;
    private _hidden: boolean = false;
    private _text: string = '';
    private _tooltip: string | null = null;
    private _icon: string | null = null;

    constructor(protected readonly priority: number) {
        this.button = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, this.priority);
    }

    protected set command(v: string | null) { this.button.command = v || undefined; }
    protected set icon(v: string | null) { this._icon = v ? `$(${v})` : null; }
    get tooltip(): string | null { return this._tooltip; }
    set tooltip(v: string | null) {
        this._tooltip = v;
        this.update();
    }

    get hidden() { return this._hidden; }
    set hidden(v: boolean) {
        this._hidden = v;
        this.update();
    }
    protected isVisible(): boolean { return !this.hidden; }

    get bracketText(): string { return `[${this._text}]`; }

    set text(text:string) {
        this._text = text;
    }

    protected getTextNormal(): string {
        if (this._text.length > 0) {
            return this.bracketText;
        }
        return '';
    }

    private _getText(icon: boolean = false): string {
        if(this._icon) {
            return this._icon;
        }
        return this.getTextNormal();
    }
    dispose(): void { this.button.dispose(); }
    update(): void {
        if (!this.isVisible() || this._forceHidden) {
            this.button.hide();
            return;
        }
        const text = this._getText(true);
        if (text === '') {
            this.button.hide();
            return;
        }
        this.button.text = text;
        this.button.tooltip = this._tooltip || undefined;
        this.button.show();
    }
}


class BuildButton extends Button {
    constructor(ext : PyMake, protected readonly priority: number) {
        super(priority);
        this.command = 'pymake.build';
        this.text = 'Build';
        this.tooltip = 'Build the selected target(s) in the terminal window';
        ext.activeTargetChanged.event((target: string) => {
            this.target = target;
        });
    }

    private _target: string | null = null;

    set target(v: string | null) {
        this._target = v;
        this.update();
    }

    protected getTooltipNormal(): string | null {
        if (!!this._target) {
            return `${this.tooltip}: [${this._target}]`;
        }
        return this.tooltip;
    }
}

class LaunchButton extends Button {
    settingsName = 'launch';
    constructor(ext: PyMake, protected readonly priority: number) {
        super(priority);
        this.command = 'pymake.run';
        this.icon = 'play';
        this.text = 'Run';
        this.tooltip = 'Launch the selected target in the terminal window';
        ext.activeTargetChanged.event((target: string) => {
            this.target = target;
        });
    }

    private _target: string | null = null;

    set target(v: string | null) {
        this._target = v;
        this.update();
    }

    protected getTooltipNormal(): string | null {
        if (!!this._target) {
            return `${this.tooltip}: [${this._target}]`;
        }
        return this.tooltip;
    }
}

class SelectTargetButton extends Button {
    constructor(ext: PyMake, protected readonly priority: number) {
        super(priority);
        this.command = 'pymake.setTarget';
        this.text = 'Select target';
        this.tooltip = 'Select build/launch/debug target';
        ext.activeTargetChanged.event((target: string) => {
            this.text = target;
            this.update();
        });
    }
}

export class StatusBar implements vscode.Disposable {

  private readonly _buttons: Button[];
  constructor(ext: PyMake) {
    this._buttons = [
        new SelectTargetButton(ext, 1),
        new LaunchButton(ext, 0.2),
        new BuildButton(ext, 0.1),
    ];
    this.update();
  }
  dispose(): void { this._buttons.forEach(btn => btn.dispose()); }
  update(): void { this._buttons.forEach(btn => btn.update()); }
}
