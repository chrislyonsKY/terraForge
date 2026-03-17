"""EarthForge ``pipeline`` command group — declarative YAML pipeline runner.

Provides commands for validating, running, listing, and initializing
EarthForge pipelines. Pipelines are YAML documents that describe a STAC
source, a set of per-item processing steps, and output configuration.
"""

from __future__ import annotations

import typer
from pydantic import BaseModel

from earthforge.core.output import render_to_console

app = typer.Typer(
    name="pipeline",
    help="Run and manage declarative geospatial pipelines.",
    no_args_is_help=True,
)


def validate(
    ctx: typer.Context,
    path: str = typer.Argument(help="Path to a pipeline YAML file."),
) -> None:
    """Validate a pipeline YAML file against the EarthForge pipeline schema."""
    from earthforge.pipeline.errors import PipelineValidationError
    from earthforge.pipeline.runner import load_pipeline
    from earthforge.pipeline.schema import validate_pipeline_doc

    try:
        doc = load_pipeline(path)
        validate_pipeline_doc(doc)
        typer.echo(f"Pipeline '{path}' is valid.")
    except PipelineValidationError as exc:
        typer.echo(f"Validation error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def run(
    ctx: typer.Context,
    path: str = typer.Argument(help="Path to a pipeline YAML file."),
    output_dir: str | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Override the pipeline's output_dir setting.",
    ),
    profile: str = typer.Option(
        "default",
        "--profile",
        help="EarthForge profile name.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and plan without executing steps.",
    ),
) -> None:
    """Execute a pipeline YAML file."""
    from earthforge.cli.main import get_state, run_command
    from earthforge.pipeline.runner import load_pipeline, run_pipeline

    state = get_state(ctx)

    doc = load_pipeline(path)
    result = run_command(
        ctx,
        run_pipeline(doc, output_dir=output_dir, profile=profile, dry_run=dry_run),
    )
    if isinstance(result, BaseModel):
        render_to_console(
            result,
            state.output,
            no_color=state.no_color,
            high_contrast=state.high_contrast,
        )


def list_steps(
    ctx: typer.Context,
) -> None:
    """List all registered pipeline step names and descriptions."""
    from earthforge.pipeline.steps import list_steps as _list

    for step in _list():
        typer.echo(f"  {step['name']:<30} {step['description']}")


def init(
    ctx: typer.Context,
    template: str = typer.Option(
        "ndvi",
        "--template",
        "-t",
        help="Starter template to generate (currently: ndvi).",
    ),
) -> None:
    """Print a starter pipeline YAML template to stdout."""
    from earthforge.pipeline.template import get_template

    try:
        typer.echo(get_template(template))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


app.command(name="validate", help="Validate a pipeline YAML file.")(validate)
app.command(name="run", help="Execute a pipeline YAML file.")(run)
app.command(name="list", help="List available pipeline steps.")(list_steps)
app.command(name="init", help="Print a starter pipeline YAML template.")(init)
