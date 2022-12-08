from pymake.core.include import include
from pymake.core.generator import generator

def cli():
    from pymake.cli import cli
    import sys
    sys.exit(cli(auto_envvar_prefix='PYMAKE'))
