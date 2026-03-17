"""EarthForge CLI entry point.

Defines the root Typer application with global flags and registers command
groups. The ``app`` object is the entry point referenced in ``pyproject.toml``
via ``[project.scripts]``.

Architecture: this module is pure dispatch. It creates the Typer app, wires
up subcommands, and defines the global callback for shared flags. No business
logic lives here.
"""

from __future__ import annotations

import typer

from earthforge.core import __version__
from earthforge.core.errors import EarthForgeError
from earthforge.core.output import OutputFormat

# ---------------------------------------------------------------------------
# Root app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="earthforge",
    help="Cloud-native geospatial developer toolkit.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)


# ---------------------------------------------------------------------------
# Global state passed to subcommands via typer.Context
# ---------------------------------------------------------------------------


class GlobalState:
    """Container for global CLI flags shared across all commands.

    Attributes:
        profile: Named config profile (default: ``"default"``).
        output: Output format (default: ``"table"``).
        verbose: Verbosity level (0 = normal, 1+ = debug).
        no_color: Whether to disable colored output.
        high_contrast: Whether to use high-contrast styling (WCAG 4.5:1).
    """

    def __init__(self) -> None:
        self.profile: str = "default"
        self.output: OutputFormat = OutputFormat.TABLE
        self.verbose: int = 0
        self.no_color: bool = False
        self.high_contrast: bool = False


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        is_eager=True,
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        help="Named config profile to use.",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--output",
        "-o",
        help="Output format: table, json, csv, quiet.",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (stackable: -vvv).",
    ),
    no_color: bool = typer.Option(
        False,
        "--no-color",
        help="Disable colored output.",
    ),
    high_contrast: bool = typer.Option(
        False,
        "--high-contrast",
        help="Use high-contrast styling for accessibility (WCAG 4.5:1).",
    ),
) -> None:
    """Cloud-native geospatial developer toolkit."""
    if version:
        typer.echo(f"earthforge {__version__}")
        raise typer.Exit()

    state = GlobalState()
    state.profile = profile
    state.output = output
    state.verbose = verbose
    state.no_color = no_color
    state.high_contrast = high_contrast
    ctx.ensure_object(dict)
    ctx.obj = state


def get_state(ctx: typer.Context) -> GlobalState:
    """Retrieve the global state from a Typer context.

    Parameters:
        ctx: The Typer command context.

    Returns:
        The :class:`GlobalState` instance set by the root callback.
    """
    state = ctx.obj
    if not isinstance(state, GlobalState):
        return GlobalState()
    return state


# ---------------------------------------------------------------------------
# Error handling wrapper
# ---------------------------------------------------------------------------


def run_command(ctx: typer.Context, coro: object) -> object:
    """Run an async command coroutine with standard error handling.

    Catches :class:`EarthForgeError` and exits with the appropriate code.
    This is the bridge between the async library layer and the sync CLI layer.

    Parameters:
        ctx: The Typer command context (for accessing global state).
        coro: An awaitable coroutine to execute.

    Returns:
        The coroutine's return value.

    Raises:
        typer.Exit: On EarthForgeError, with the error's exit code.
    """
    import asyncio

    try:
        return asyncio.run(coro)  # type: ignore[arg-type]
    except EarthForgeError as exc:
        state = get_state(ctx)
        if state.verbose > 0:
            typer.echo(f"Error ({type(exc).__name__}): {exc}", err=True)
        else:
            typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=exc.exit_code) from exc


# ---------------------------------------------------------------------------
# Register command groups
# ---------------------------------------------------------------------------

# Import and register subcommand modules. These are guarded imports so the CLI
# can still show --help even if an optional domain package is not installed.

from earthforge.cli.commands import bench_cmd as _bench_cmd  # noqa: E402
from earthforge.cli.commands import completions_cmd as _completions_cmd  # noqa: E402
from earthforge.cli.commands import config_cmd as _config_cmd  # noqa: E402
from earthforge.cli.commands import cube_cmd as _cube_cmd  # noqa: E402
from earthforge.cli.commands import explore_cmd as _explore_cmd  # noqa: E402
from earthforge.cli.commands import info as _info_cmd  # noqa: E402
from earthforge.cli.commands import pipeline_cmd as _pipeline_cmd  # noqa: E402
from earthforge.cli.commands import raster_cmd as _raster_cmd  # noqa: E402
from earthforge.cli.commands import stac_cmd as _stac_cmd  # noqa: E402
from earthforge.cli.commands import vector_cmd as _vector_cmd  # noqa: E402

app.command(name="info", help="Inspect a geospatial file (auto-detects format).")(_info_cmd.info)
app.command(name="completions", help="Print a shell completion script (bash/zsh/fish).")(
    _completions_cmd.completions
)
app.add_typer(_config_cmd.app)
app.add_typer(_stac_cmd.app)
app.add_typer(_raster_cmd.app)
app.add_typer(_vector_cmd.app)
app.add_typer(_cube_cmd.app)
app.add_typer(_pipeline_cmd.app)
app.add_typer(_bench_cmd.app)
app.add_typer(_explore_cmd.app)
