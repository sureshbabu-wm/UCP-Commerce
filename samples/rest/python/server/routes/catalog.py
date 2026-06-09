#   Copyright 2026 UCP Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""Catalog API routes.

Exposes the SQLite product catalog via REST endpoints so agents and
external callers can search and look up products without direct DB access.
"""

import logging
from typing import Annotated

import dependencies
import db
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ucp_sdk.models.schemas.shopping.types.item import Item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/catalog", tags=["catalog"])


class CatalogSearchResponse(BaseModel):
    """Schema for the catalog search response."""
    query: str | None = None
    count: int
    results: list[Item]


def _product_to_item(product: db.Product) -> Item:
    """Serialize a Product ORM object to a standard UCP Item."""
    return Item(
        id=product.id,
        title=product.title,
        price=product.price,
        image_url=product.image_url if product.image_url else None,
    )


@router.get("/search", response_model=CatalogSearchResponse)
async def search_products(
    q: Annotated[str | None, Query(description="Search term to match against product title")] = None,
    limit: Annotated[int, Query(description="Max number of results to return", ge=1, le=100)] = 20,
    products_session: AsyncSession = Depends(dependencies.get_products_db),
) -> CatalogSearchResponse:
    """Search products by title. Returns all if no query given."""
    stmt = select(db.Product)
    if q:
        stmt = stmt.where(db.Product.title.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)
    result = await products_session.execute(stmt)
    products = result.scalars().all()
    return CatalogSearchResponse(
        query=q,
        count=len(products),
        results=[_product_to_item(p) for p in products],
    )


@router.get("/lookup/{product_id}", response_model=Item)
async def lookup_product(
    product_id: str,
    products_session: AsyncSession = Depends(dependencies.get_products_db),
) -> Item:
    """Look up a single product by its ID."""
    product = await db.get_product(products_session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found.")
    return _product_to_item(product)

