from pkg_resources import DistributionNotFound, get_distribution

try:
    __version__ = get_distribution("snapcat").version
except DistributionNotFound:
    # package is not installed
    __version__ = "unknown"


import rich_click as click

from snapcat.sync_cmd import sync
from snapcat.export_cmd import export
from snapcat.show_cmd import show


@click.group()
@click.version_option(prog_name="snapcat", version=__version__)
@click.pass_context
@click.option(
    "-f",
    "--file-name",
    "db_file_name",
    required=False,
    default=None,
    help="The name of the database file (default: <tail_hash>.db)",
)
def cli(ctx, db_file_name: str):
    ctx.ensure_object(dict)
    ctx.obj["db_file_name"] = db_file_name


cli.add_command(sync)
cli.add_command(export)
cli.add_command(show)
