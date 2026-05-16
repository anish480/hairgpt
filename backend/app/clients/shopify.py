import time
from dataclasses import dataclass

import httpx

from app.clients.secret_manager import get_secret
from app.config import settings


@dataclass
class _CachedToken:
    value: str
    expires_at: float


_cache: _CachedToken | None = None
_REFRESH_MARGIN_S = 300


async def mint_admin_token(shop: str | None = None) -> str:
    global _cache
    shop = shop or settings.shopify_shop
    now = time.time()
    if _cache and _cache.expires_at - _REFRESH_MARGIN_S > now:
        return _cache.value

    client_id = get_secret(settings.shopify_client_id_secret)
    client_secret = get_secret(settings.shopify_client_secret_secret)

    async with httpx.AsyncClient(timeout=10.0) as http:
        r = await http.post(
            f"https://{shop}.myshopify.com/admin/oauth/access_token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        r.raise_for_status()
        body = r.json()

    _cache = _CachedToken(value=body["access_token"], expires_at=now + body["expires_in"])
    return _cache.value


async def admin_graphql(query: str, variables: dict | None = None, shop: str | None = None) -> dict:
    shop = shop or settings.shopify_shop
    token = await mint_admin_token(shop)
    url = f"https://{shop}.myshopify.com/admin/api/{settings.shopify_api_version}/graphql.json"
    async with httpx.AsyncClient(timeout=20.0) as http:
        r = await http.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": token,
            },
            json={"query": query, "variables": variables or {}},
        )
        r.raise_for_status()
        return r.json()
