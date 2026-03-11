"""EarthForge ``config`` command group — manage configuration profiles.

Provides commands for initializing, viewing, and managing EarthForge
configuration profiles. Profiles control STAC API endpoints, cloud storage
backends, and authentication settings.
"""

from __future__ import annotations

import typer

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="config",
    help="Manage EarthForge configuration profiles.",
    no_args_is_help=True,
)


def init(
    ctx: typer.Context,
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Overwrite existing config file.",
    ),
) -> None:
    """Create a default configuration file."""
    from earthforge.cli.main import run_command
    from earthforge.core.config import init_config

    result = run_command(ctx, init_config(overwrite=overwrite))
    if result is not None:
        typer.echo(f"Config file created: {result}")


def show(
    ctx: typer.Context,
) -> None:
    """Show the active profile configuration."""
    from pydantic import BaseModel, Field

    from earthforge.cli.main import get_state, run_command
    from earthforge.core.config import EarthForgeProfile, load_profile

    class ProfileView(BaseModel):
        """Rendered view of a profile for CLI output."""

        name: str = Field(title="Profile")
        stac_api: str | None = Field(default=None, title="STAC API")
        storage_backend: str = Field(title="Storage")
        storage_options: dict[str, str] = Field(default_factory=dict, title="Options")

    state = get_state(ctx)
    result = run_command(ctx, load_profile(state.profile))

    if isinstance(result, EarthForgeProfile):
        view = ProfileView(
            name=result.name,
            stac_api=result.stac_api,
            storage_backend=result.storage_backend,
            storage_options=result.storage_options,
        )
        render_to_console(view, state.output, no_color=state.no_color)


app.command(name="init", help="Create a default configuration file.")(init)
app.command(name="show", help="Show the active profile configuration.")(show)
