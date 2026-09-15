"""
CIVIS command-line entry point.

Wired with Typer. Subcommands live in sibling modules (session.py for
fase A; others will land in later phases). This file assembles the app
and exports `main` so `python -m civis` and `python -m civis.cli` find it.
"""

import typer

from civis.cli.session import session_command

# no_args_is_help=True prints help when the user runs `python -m civis` with
# nothing. add_completion=False keeps the surface small; shell completion is
# a wk-6 concern.
app = typer.Typer(
    help="CIVIS — Virtual Citizen Simulator for public-service agent training.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root_callback() -> None:
    """
    Root callback exists solely to force Typer to render `civis` as a
    subcommand app rather than promoting the single command to root.
    Without this, Typer would flatten `civis session` into just `civis`.
    """


app.command("session", help="Run one training session with an agent + persona.")(
    session_command
)


def main() -> None:
    """Entry point used by `python -m civis`."""
    app()


if __name__ == "__main__":
    main()
