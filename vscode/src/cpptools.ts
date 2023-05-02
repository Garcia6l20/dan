// /**
//  * Module for vscode-cpptools integration.
//  *
//  * This module uses the [vscode-cpptools API](https://www.npmjs.com/package/vscode-cpptools)
//  * to provide that extension with per-file configuration information.
import * as path from 'path';
import * as vscode from 'vscode';
import * as cpt from 'vscode-cpptools';
import { codeCommand } from './pymake/commands';
import { PyMake } from './extension';

/**
 * The actual class that provides information to the cpptools extension. See
 * the `CustomConfigurationProvider` interface for information on how this class
 * should be used.
 */
export class ConfigurationProvider implements cpt.CustomConfigurationProvider {
    /** Our name visible to cpptools */
    readonly name = 'PyMake';
    /** Our extension ID, visible to cpptools */
    readonly extensionId = 'pymake';

    constructor(private ext: PyMake) {}

    private getSourcesConfiguration(uris: vscode.Uri[]) {
        return codeCommand<cpt.SourceFileConfigurationItem[]>(this.ext, 'get-source-configuration', ...uris.map(u => u.fsPath));
    }

    private getWorkspaceBrowseConfiguration() {
        return codeCommand<cpt.WorkspaceBrowseConfiguration>(this.ext, 'get-workspace-browse-configuration');
    }

    /**
     * Test if we are able to provide a configuration for the given URI
     * @param uri The URI to look up
     */
    async canProvideConfiguration(uri: vscode.Uri): Promise<boolean> {        
        const configs = await this.getSourcesConfiguration([uri]);
        return configs.length !== 0;
    }

    /**
     * Get the configurations for the given URIs. URIs for which we have no
     * configuration are simply ignored.
     * @param uris The file URIs to look up
     */
    async provideConfigurations(uris: vscode.Uri[]): Promise<cpt.SourceFileConfigurationItem[]> {
        return this.getSourcesConfiguration(uris);
    }

    /**
     * A request to determine whether this provider can provide a code browsing configuration for the workspace folder.
     * @param token (optional) The cancellation token.
     * @returns 'true' if this provider can provider a code browsing configuration for the workspace folder.
     */
    async canProvideBrowseConfiguration(): Promise<boolean> { return true; }

    /**
     * A request to get the code browsing configuration for the workspace folder.
     * @returns A [WorkspaceBrowseConfiguration](#WorkspaceBrowseConfiguration) with the information required to
     * construct the equivalent of `browse.path` from `c_cpp_properties.json`.
     */
    async provideBrowseConfiguration(): Promise<cpt.WorkspaceBrowseConfiguration> {
        return this.getWorkspaceBrowseConfiguration();
    }

    async canProvideBrowseConfigurationsPerFolder(): Promise<boolean> { return false; }

    async provideFolderBrowseConfiguration(_uri: vscode.Uri): Promise<cpt.WorkspaceBrowseConfiguration> {
        return this.getWorkspaceBrowseConfiguration();
    }

    /** No-op */
    dispose() { }
}
