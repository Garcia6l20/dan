
import json
from dan.core.pathlib import Path
import subprocess


class CompileCommands:
    def __init__(self, path) -> None:
        self.cc_path: Path = path / 'compile_commands.json'
        if self.cc_path.exists():
            with open(self.cc_path, 'r') as cc_f:
                try:
                    self.data = json.load(cc_f)
                except json.JSONDecodeError:
                    self.data = list()
        else:
            self.data = list()
            self.cc_path.parent.mkdir(parents=True, exist_ok=True)

    def clear(self):
        with open(self.cc_path, 'w'):
            pass

    def update(self):
        with open(self.cc_path, 'w') as cc_f:
            json.dump(self.data, cc_f)

    def get(self, file: Path):
        fname = file.name
        for entry in self.data:
            if entry['file'] == fname:
                return entry
        return None

    def insert(self, file: Path, build_path: Path, content: list[str] | str):
        entry = self.get(file)
        if isinstance(content, list):
            content = subprocess.list2cmdline(content)

        if entry:
            entry['command'] = content
        else:
            self.data.append({
                'file': str(file),
                'directory': str(build_path),
                'command': content
            })
