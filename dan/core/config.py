from dan.config.context import ConfigContext

from pathlib import Path

import importlib.util

def load_project_config(source_path: Path):
    config_path = source_path / 'dan-config.py'
    if config_path.exists():
        spec = importlib.util.spec_from_file_location(
            'dan.config.current', config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
