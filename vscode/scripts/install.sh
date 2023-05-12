#!/usr/bin/env bash

this_path=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
root=$this_path/..

if ! [ -x "$(command -v npm)" ]; then
    echo 'Error: npm is not installed.' >&2
    exit 1
fi

# install or update vsce
npm install -g @vscode/vsce

(cd $root && vsce package)


version=$(cat package.json | python -c "import sys, json; print(json.load(sys.stdin)['version'])")

code --install-extension $root/pymake-$version.vsix
