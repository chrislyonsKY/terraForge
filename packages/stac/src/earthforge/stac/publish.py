"""STAC item publication to writable STAC APIs.

Pushes STAC items to APIs that support the Transaction Extension
(OGC API - Features - Part 4). Checks the ``/conformance`` endpoint
before attempting to POST/PUT items.

Usage::

    from earthforge.stac.publish import publish_item

    profile = await load_profile("default")
    result = await publish_item(profile, item_dict, collection_id="my-collection")
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from earthforge.stac.errors import StacPublishError

if TYPE_CHECKING:
    from earthforge.core.config import EarthForgeProfile


_TRANSACTION_CONFORMANCE = [
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/simpletx",
    "https://api.stacspec.org/v0.1.0/ogcfeat/extensions/transaction",
]


class PublishResult(BaseModel):
    """Result of publishing a STAC item.

    Attributes:
        item_id: The published item's ID.
        collection_id: The target collection.
        api_url: The STAC API endpoint.
        action: ``"created"`` or ``"updated"``.
        status_code: HTTP response status code.
        self_link: URL to the published item (if available).
    """

    item_id: str = Field(title="Item ID")
    collection_id: str = Field(title="Collection")
    api_url: str = Field(title="API URL")
    action: str = Field(title="Action")
    status_code: int = Field(title="Status Code")
    self_link: str | None = Field(default=None, title="Self Link")


async def check_transaction_support(api_url: str) -> bool:
    """Check if a STAC API supports the Transaction Extension.

    Parameters:
        api_url: Base URL of the STAC API.

    Returns:
        True if the Transaction Extension is supported.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_check_transaction_sync, api_url))


def _check_transaction_sync(api_url: str) -> bool:
    """Synchronous conformance check."""
    import httpx

    conformance_url = api_url.rstrip("/") + "/conformance"
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(conformance_url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return False

    conforms_to = data.get("conformsTo", [])
    return any(
        conf in conforms_to
        for conf in _TRANSACTION_CONFORMANCE
    )


async def publish_item(
    profile: EarthForgeProfile,
    item: dict[str, Any],
    *,
    collection_id: str | None = None,
    api_url: str | None = None,
    upsert: bool = True,
) -> PublishResult:
    """Publish a STAC item to a writable STAC API.

    Parameters:
        profile: EarthForge profile (provides default STAC API URL).
        item: STAC Item dict to publish.
        collection_id: Target collection. Defaults to item's ``collection`` field.
        api_url: Override STAC API URL. Defaults to profile's ``stac_api``.
        upsert: If True, attempt PUT to update if POST returns 409 Conflict.

    Returns:
        A :class:`PublishResult` with publication details.

    Raises:
        StacPublishError: If publication fails.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _publish_sync, profile, item,
            collection_id=collection_id, api_url=api_url, upsert=upsert,
        ),
    )


def _publish_sync(
    profile: Any,
    item: dict[str, Any],
    *,
    collection_id: str | None = None,
    api_url: str | None = None,
    upsert: bool = True,
) -> PublishResult:
    """Synchronous item publication."""
    import httpx

    base_url = api_url or getattr(profile, "stac_api", None)
    if not base_url:
        raise StacPublishError("No STAC API URL configured in profile or --api-url")

    base_url = base_url.rstrip("/")
    coll_id = collection_id or item.get("collection")
    if not coll_id:
        raise StacPublishError(
            "No collection_id specified and item has no 'collection' field"
        )

    item_id = item.get("id")
    if not item_id:
        raise StacPublishError("Item must have an 'id' field")

    # Ensure item has correct collection field
    item["collection"] = coll_id

    items_url = f"{base_url}/collections/{coll_id}/items"
    item_url = f"{items_url}/{item_id}"

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            # Try POST first (create)
            resp = client.post(items_url, json=item)

            if resp.status_code in (200, 201):
                action = "created"
                status_code = resp.status_code
            elif resp.status_code == 409 and upsert:
                # Conflict — try PUT to update
                resp = client.put(item_url, json=item)
                if resp.status_code in (200, 204):
                    action = "updated"
                    status_code = resp.status_code
                else:
                    raise StacPublishError(
                        f"PUT failed with status {resp.status_code}: {resp.text}"
                    )
            else:
                raise StacPublishError(
                    f"POST failed with status {resp.status_code}: {resp.text}"
                )
    except StacPublishError:
        raise
    except Exception as exc:
        raise StacPublishError(f"HTTP request failed: {exc}") from exc

    # Try to extract self link from response
    self_link = None
    try:
        resp_data = resp.json()
        links = resp_data.get("links", [])
        self_link = next(
            (lnk["href"] for lnk in links if lnk.get("rel") == "self"),
            None,
        )
    except Exception:
        self_link = item_url

    return PublishResult(
        item_id=item_id,
        collection_id=coll_id,
        api_url=base_url,
        action=action,
        status_code=status_code,
        self_link=self_link,
    )
