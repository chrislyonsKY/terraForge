"""Pipeline-domain error types for EarthForge."""

from earthforge.core.errors import EarthForgeError


class PipelineError(EarthForgeError):
    """Raised when a pipeline operation fails.

    Covers schema validation errors, missing step handlers, source fetch
    failures, and step execution errors.
    """


class PipelineValidationError(PipelineError):
    """Raised when a pipeline YAML document fails schema validation."""

    def __init__(self, message: str, path: str | None = None) -> None:
        location = f" at {path}" if path else ""
        super().__init__(f"Pipeline validation error{location}: {message}")


class StepError(PipelineError):
    """Raised when a pipeline step fails during execution."""

    def __init__(self, step_name: str, item_id: str, cause: str) -> None:
        super().__init__(f"Step '{step_name}' failed for item '{item_id}': {cause}")
        self.step_name = step_name
        self.item_id = item_id
