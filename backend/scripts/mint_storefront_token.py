"""Mint a long-lived Storefront API access token via the Admin API and push it
to Secret Manager.

Run once per store:
    uv run python -m scripts.mint_storefront_token moxie-dev-store-soqsybgm
    uv run python -m scripts.mint_storefront_token moxiebeauty-haircare

The minted token inherits the calling app's `unauthenticated_*` scopes and is
suitable for both backend ingestion and the browser widget.
"""

from __future__ import annotations

import asyncio
import sys

from google.cloud import secretmanager

from app.clients.shopify import admin_graphql
from app.config import settings

SHOP_TO_SECRET = {
    "moxie-dev-store-soqsybgm": "shopify-storefront-token-dev",
    "moxiebeauty-haircare": "shopify-storefront-token-main",
}

MUTATION = """
mutation StorefrontAccessTokenCreate($input: StorefrontAccessTokenInput!) {
  storefrontAccessTokenCreate(input: $input) {
    storefrontAccessToken {
      id
      title
      accessToken
      accessScopes { handle }
    }
    userErrors { field message }
  }
}
"""


def _push_secret(secret_id: str, value: str) -> None:
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{settings.gcp_project_id}/secrets/{secret_id}"
    client.add_secret_version(parent=parent, payload={"data": value.encode("utf-8")})


async def mint(shop: str) -> None:
    if shop not in SHOP_TO_SECRET:
        print(f"[mint] unknown shop {shop!r}; add it to SHOP_TO_SECRET", file=sys.stderr)
        sys.exit(2)
    secret_id = SHOP_TO_SECRET[shop]

    print(f"[mint] calling storefrontAccessTokenCreate on {shop}.myshopify.com ...")
    resp = await admin_graphql(
        MUTATION,
        variables={"input": {"title": "hairgpt-backend"}},
        shop=shop,
    )
    if errors := resp.get("errors"):
        print(f"[mint] GraphQL errors: {errors}", file=sys.stderr)
        sys.exit(1)
    payload = resp["data"]["storefrontAccessTokenCreate"]
    if user_errors := payload.get("userErrors"):
        print(f"[mint] userErrors: {user_errors}", file=sys.stderr)
        sys.exit(1)

    sat = payload["storefrontAccessToken"]
    scopes = [s["handle"] for s in sat["accessScopes"]]
    print(f"[mint] token created (title={sat['title']!r}, scopes={scopes})")

    _push_secret(secret_id, sat["accessToken"])
    print(f"[mint] pushed new version of secret {secret_id}")


async def verify(shop: str) -> None:
    secret_id = SHOP_TO_SECRET[shop]
    client = secretmanager.SecretManagerServiceClient()
    token = client.access_secret_version(
        name=f"projects/{settings.gcp_project_id}/secrets/{secret_id}/versions/latest"
    ).payload.data.decode("utf-8")

    import httpx

    url = f"https://{shop}.myshopify.com/api/{settings.shopify_api_version}/graphql.json"
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Storefront-Access-Token": token,
            },
            json={"query": "{ shop { name primaryDomain { url } } }"},
        )
        r.raise_for_status()
        data = r.json()

    if errs := data.get("errors"):
        print(f"[verify] Storefront API errors: {errs}", file=sys.stderr)
        sys.exit(1)
    name = data["data"]["shop"]["name"]
    print(f"[verify] Storefront API OK — shop name: {name}")


async def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m scripts.mint_storefront_token <shop_handle>", file=sys.stderr)
        sys.exit(2)
    shop = sys.argv[1]
    await mint(shop)
    await verify(shop)


if __name__ == "__main__":
    asyncio.run(main())
