from dan.cli.main import user_cli as cli, Make
from dan.cli.main import click

command = cli.command
group = cli.group
pass_make = click.make_pass_decorator(Make)
