"""Consolidated CLI for OpenTrack tools using a plugin architecture."""

import typer

# Import CLI subcommands from plugins
from opentrack_admin.cli import app as admin_app
from opentrack_reports.cli import app as reports_app

# Create main application
app = typer.Typer(
    name="opentrack",
    help="OpenTrack event administration and reporting tools",
    no_args_is_help=True,
)

# Register plugin subcommands
app.add_typer(admin_app, name="admin", help="Event administration commands")
app.add_typer(reports_app, name="reports", help="Generate reports and documents")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
