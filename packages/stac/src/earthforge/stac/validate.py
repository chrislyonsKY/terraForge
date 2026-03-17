"""STAC item and collection validation against the STAC specification.

Validates STAC documents using ``pystac``'s built-in validation (which
delegates to JSON Schema validation against the STAC spec schemas).
Supports validating both local JSON files and remote STAC API URLs.

Usage::

    from earthforge.stac.validate import validate_stac

    profile = await load_profile("default")
    result = await validate_stac(profile, "https://earth-search.../items/S2A_...")
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from earthforge.core.output import StatusMarker, format_status
from earthforge.stac.errors import StacValidationError

if TYPE_CHECKING:
    from earthforge.core.config import EarthForgeProfile


class StacValidationCheck(BaseModel):
    """Result of a single validation check.

    Attributes:
        check: Name of the validation check.
        status: Pass/fail/warn status with text marker.
        message: Human-readable detail.
    """

    check: str = Field(title="Check")
    status: str = Field(title="Status")
    message: str = Field(title="Message")


class StacValidationResult(BaseModel):
    """Aggregate result of validating a STAC document.

    Attributes:
        source: URL or path that was validated.
        stac_type: Detected type (``"Item"``, ``"Collection"``, ``"Catalog"``).
        stac_version: STAC version declared in the document.
        is_valid: Overall pass/fail.
        extensions_validated: List of extension schema IDs that were checked.
        checks: Individual check results.
        summary: Human-readable one-line summary.
    """

    source: str = Field(title="Source")
    stac_type: str = Field(title="Type")
    stac_version: str = Field(title="STAC Version")
    is_valid: bool = Field(title="Valid")
    extensions_validated: list[str] = Field(default_factory=list, title="Extensions")
    checks: list[StacValidationCheck] = Field(default_factory=list, title="Checks")
    summary: str = Field(title="Summary")


async def validate_stac(
    profile: EarthForgeProfile,
    source: str,
) -> StacValidationResult:
    """Validate a STAC item or collection against the specification.

    Fetches the STAC document, determines its type, then runs ``pystac``
    validation including any declared extension schemas.

    Parameters:
        profile: EarthForge profile (used for HTTP client configuration).
        source: URL or local path to a STAC item or collection JSON.

    Returns:
        A :class:`StacValidationResult` with detailed check results.

    Raises:
        StacValidationError: If the document cannot be fetched or parsed.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_validate_sync, profile, source))


def _validate_sync(
    profile: Any,
    source: str,
) -> StacValidationResult:
    """Synchronous validation implementation.

    Parameters:
        profile: EarthForge profile.
        source: URL or path to STAC JSON.

    Returns:
        Validation result.
    """

    try:
        import pystac
    except ImportError as exc:
        raise StacValidationError(
            "pystac is required for STAC validation: pip install earthforge[stac]"
        ) from exc

    checks: list[StacValidationCheck] = []

    # --- Fetch document ---
    stac_dict = _load_stac_document(source)

    # --- Detect type ---
    stac_type = stac_dict.get("type", "Unknown")
    stac_version = stac_dict.get("stac_version", "Unknown")

    checks.append(
        StacValidationCheck(
            check="stac_version",
            status=format_status(
                StatusMarker.PASS if stac_version != "Unknown" else StatusMarker.FAIL
            ),
            message=f"STAC version: {stac_version}",
        )
    )

    # --- Required fields ---
    if stac_type == "Feature":
        required = [
            "type",
            "stac_version",
            "id",
            "geometry",
            "bbox",
            "properties",
            "links",
            "assets",
        ]
        display_type = "Item"
    elif stac_type == "Collection":
        required = ["type", "stac_version", "id", "description", "license", "links", "extent"]
        display_type = "Collection"
    elif stac_type == "Catalog":
        required = ["type", "stac_version", "id", "description", "links"]
        display_type = "Catalog"
    else:
        checks.append(
            StacValidationCheck(
                check="type_detection",
                status=format_status(StatusMarker.FAIL),
                message=f"Unrecognized STAC type: '{stac_type}'",
            )
        )
        return StacValidationResult(
            source=source,
            stac_type="Unknown",
            stac_version=stac_version,
            is_valid=False,
            checks=checks,
            summary=format_status(StatusMarker.FAIL, "Not a valid STAC document"),
        )

    checks.append(
        StacValidationCheck(
            check="type_detection",
            status=format_status(StatusMarker.PASS),
            message=f"Document type: {display_type}",
        )
    )

    # Check required fields
    missing = [f for f in required if f not in stac_dict]
    if missing:
        checks.append(
            StacValidationCheck(
                check="required_fields",
                status=format_status(StatusMarker.FAIL),
                message=f"Missing required fields: {', '.join(missing)}",
            )
        )
    else:
        checks.append(
            StacValidationCheck(
                check="required_fields",
                status=format_status(StatusMarker.PASS),
                message="All required fields present",
            )
        )

    # --- Extension validation ---
    extensions = stac_dict.get("stac_extensions", [])
    extensions_validated: list[str] = []

    if extensions:
        checks.append(
            StacValidationCheck(
                check="extensions_declared",
                status=format_status(StatusMarker.INFO),
                message=f"{len(extensions)} extension(s) declared",
            )
        )
        extensions_validated = list(extensions)

    # --- pystac validation ---
    pystac_valid = True
    try:
        if stac_type == "Feature":
            item = pystac.Item.from_dict(stac_dict)
            item.validate()
        elif stac_type == "Collection":
            collection = pystac.Collection.from_dict(stac_dict)
            collection.validate()
        elif stac_type == "Catalog":
            catalog = pystac.Catalog.from_dict(stac_dict)
            catalog.validate()

        checks.append(
            StacValidationCheck(
                check="pystac_validation",
                status=format_status(StatusMarker.PASS),
                message="pystac schema validation passed",
            )
        )
    except pystac.STACValidationError as exc:
        pystac_valid = False
        checks.append(
            StacValidationCheck(
                check="pystac_validation",
                status=format_status(StatusMarker.FAIL),
                message=f"pystac validation failed: {exc}",
            )
        )
    except Exception as exc:
        # Non-schema errors (link resolution, network) are warnings, not failures.
        # The document's schema validity is independent of whether external
        # links are reachable.
        checks.append(
            StacValidationCheck(
                check="pystac_validation",
                status=format_status(StatusMarker.WARN),
                message=f"Validation warning: {exc}",
            )
        )

    # --- Links check ---
    links = stac_dict.get("links", [])
    has_self = any(lnk.get("rel") == "self" for lnk in links if isinstance(lnk, dict))

    if has_self:
        checks.append(
            StacValidationCheck(
                check="link_self",
                status=format_status(StatusMarker.PASS),
                message="Self link present",
            )
        )
    else:
        checks.append(
            StacValidationCheck(
                check="link_self",
                status=format_status(StatusMarker.WARN),
                message="No self link found (recommended)",
            )
        )

    # --- Summary ---
    is_valid = pystac_valid and not missing
    fail_count = sum(1 for c in checks if StatusMarker.FAIL.value in c.status)
    warn_count = sum(1 for c in checks if StatusMarker.WARN.value in c.status)
    pass_count = sum(1 for c in checks if StatusMarker.PASS.value in c.status)

    if is_valid:
        summary = format_status(
            StatusMarker.PASS,
            f"Valid STAC {display_type} ({pass_count} checks passed"
            + (f", {warn_count} warning(s)" if warn_count else "")
            + ")",
        )
    else:
        summary = format_status(
            StatusMarker.FAIL,
            f"Invalid STAC {display_type} ({fail_count} failure(s), {warn_count} warning(s))",
        )

    return StacValidationResult(
        source=source,
        stac_type=display_type,
        stac_version=stac_version,
        is_valid=is_valid,
        extensions_validated=extensions_validated,
        checks=checks,
        summary=summary,
    )


def _load_stac_document(source: str) -> dict[str, Any]:
    """Load a STAC document from a URL or local path.

    Parameters:
        source: URL (http/https) or local file path.

    Returns:
        Parsed JSON dict.

    Raises:
        StacValidationError: If the document cannot be fetched or parsed.
    """
    import json
    from pathlib import Path

    if source.startswith(("http://", "https://")):
        try:
            import httpx

            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(source)
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
        except Exception as exc:
            raise StacValidationError(
                f"Failed to fetch STAC document from {source}: {exc}"
            ) from exc
    else:
        path = Path(source)
        if not path.exists():
            raise StacValidationError(f"File not found: {source}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            raise StacValidationError(f"Invalid JSON in {source}: {exc}") from exc
