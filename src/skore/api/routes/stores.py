"""The definition of API routes to list stores and get them."""

import os
from pathlib import Path
from typing import Any, Iterable

import fastapi
from fastapi import APIRouter, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.templating import Jinja2Templates

from skore import registry
from skore.api import schema
from skore.storage import URI, FileSystem
from skore.store.layout import Layout
from skore.store.store import Store, _get_storage_path

SKORES_ROUTER = APIRouter(prefix="/skores", deprecated=True)
STORES_ROUTER = APIRouter(prefix="/stores")

# TODO Move this to a more appropriate place
STATIC_FILES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "dashboard" / "static"
)


def serialize_store(store: Store):
    """Serialize a Store."""
    # mypy does not understand union in generator
    user_items: Iterable[tuple[str, Any, dict]] = filter(
        lambda i: i[0] != Store.LAYOUT_KEY,
        store.items(metadata=True),  # type: ignore
    )

    payload: dict = {}
    for key, value, metadata in user_items:
        payload[key] = {
            "type": str(metadata["display_type"]),
            "data": value,
            "metadata": metadata,
        }

    layout = store.get_layout()

    model = schema.Store(
        schema="schema:dashboard:v0",
        uri=str(store.uri),
        payload=payload,
        layout=layout,
    )

    return model.model_dump(by_alias=True)


@SKORES_ROUTER.get("/share/{uri:path}")
@STORES_ROUTER.get("/share/{uri:path}")
async def share_store(request: fastapi.Request, uri: str):
    """Serve an inlined shareable HTML page."""

    # Get static assets to inject them into the report template
    def read_asset_content(path):
        with open(STATIC_FILES_PATH / path) as f:
            return f.read()

    script_content = read_asset_content("skore.umd.cjs")
    styles_content = read_asset_content("style.css")

    # Get Skore and serialize it
    directory = _get_storage_path(os.environ.get("SKORE_ROOT"))
    storage = FileSystem(directory=directory)
    store = registry.find_store_by_uri(URI(uri), storage)
    if store is None:
        raise HTTPException(status_code=404, detail=f"No store found in '{uri}'")

    store_data = jsonable_encoder(serialize_store(store))

    # Fill the Jinja context
    context = {
        "uri": store.uri,
        "store_data": store_data,
        "script": script_content,
        "styles": styles_content,
    }

    # Render the template and send the result
    templates = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")
    return templates.TemplateResponse(
        request=request, name="share.html.jinja", context=context
    )


@SKORES_ROUTER.get("")
@SKORES_ROUTER.get("/")
@STORES_ROUTER.get("")
@STORES_ROUTER.get("/")
async def list_stores() -> list[str]:
    """Route used to list the URI of stores."""
    directory = _get_storage_path(os.environ.get("SKORE_ROOT"))
    storage = FileSystem(directory=directory)

    return sorted(str(store.uri) for store in registry.stores(storage))


@SKORES_ROUTER.get("/{uri:path}")
@STORES_ROUTER.get("/{uri:path}")
async def get_store_by_uri(uri: str):
    """Route used to get a store by its URI."""
    directory = _get_storage_path(os.environ.get("SKORE_ROOT"))
    storage = FileSystem(directory=directory)

    store = registry.find_store_by_uri(URI(uri), storage)
    if store is not None:
        return serialize_store(store)

    raise HTTPException(status_code=404, detail=f"No store found in '{uri}'")


@SKORES_ROUTER.put("/{uri:path}/layout", status_code=status.HTTP_201_CREATED)
@STORES_ROUTER.put("/{uri:path}/layout", status_code=status.HTTP_201_CREATED)
async def put_layout(uri: str, payload: Layout):
    """Save the report layout configuration."""
    directory = _get_storage_path(os.environ.get("SKORE_ROOT"))
    storage = FileSystem(directory=directory)

    store = registry.find_store_by_uri(URI(uri), storage)
    if store is not None:
        store.set_layout(payload)
        return serialize_store(store)

    raise HTTPException(status_code=404, detail=f"No store found in '{uri}'")