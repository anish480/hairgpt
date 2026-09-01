"""Reconcile Shopify orders with HairGPT sessions.

Queries Shopify Admin API for recent orders, finds line items tagged with
_hairgpt_session property, and writes attribution data to hairgpt_conversions.

Usage:
    python reconcile_conversions.py              # last 24 hours
    python reconcile_conversions.py --days 7     # last 7 days
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.clients.shopify import admin_graphql
from app.db import get_pool

ORDERS_QUERY = """
query($query: String!, $after: String) {
  orders(first: 50, after: $after, query: $query) {
    edges {
      node {
        id
        name
        createdAt
        totalPriceSet { shopMoney { amount currencyCode } }
        lineItems(first: 50) {
          edges {
            node {
              title
              quantity
              originalTotalSet { shopMoney { amount } }
              customAttributes { key value }
            }
          }
        }
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
"""


def extract_attributions(order_node: dict) -> list[dict]:
    """Extract HairGPT-attributed line items from an order."""
    order_id = order_node["id"]
    order_number = order_node["name"]
    order_total = float(order_node["totalPriceSet"]["shopMoney"]["amount"])
    order_created = isoparse(order_node["createdAt"])

    total_items = 0
    hairgpt_items = 0
    hairgpt_revenue = 0.0
    sessions = set()

    for edge in order_node["lineItems"]["edges"]:
        item = edge["node"]
        total_items += item["quantity"]
        attrs = {a["key"]: a["value"] for a in (item.get("customAttributes") or [])}
        session_id = attrs.get("_hairgpt_session")
        if session_id:
            sessions.add(session_id)
            hairgpt_items += item["quantity"]
            hairgpt_revenue += float(item["originalTotalSet"]["shopMoney"]["amount"])

    results = []
    for session_id in sessions:
        results.append({
            "session_id": session_id,
            "shopify_order_id": order_id,
            "order_number": order_number,
            "order_total": order_total,
            "hairgpt_revenue": hairgpt_revenue,
            "hairgpt_items": hairgpt_items,
            "total_items": total_items,
            "order_created_at": order_created,
        })
    return results


async def fetch_orders(since: datetime) -> list[dict]:
    """Paginate through all orders since the given datetime."""
    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    query_filter = f"created_at:>='{since_str}'"
    all_orders = []
    after = None

    while True:
        result = await admin_graphql(ORDERS_QUERY, {"query": query_filter, "after": after})
        orders_data = result.get("data", {}).get("orders", {})
        edges = orders_data.get("edges", [])
        all_orders.extend(edge["node"] for edge in edges)

        page_info = orders_data.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            after = page_info["endCursor"]
        else:
            break

    return all_orders


async def reconcile(days: int = 1):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    print(f"Fetching orders since {since.isoformat()}...")

    orders = await fetch_orders(since)
    print(f"Found {len(orders)} orders")

    attributions = []
    for order in orders:
        attributions.extend(extract_attributions(order))

    if not attributions:
        print("No HairGPT-attributed orders found")
        return

    print(f"Found {len(attributions)} HairGPT-attributed orders")

    pool = await get_pool()
    async with pool.acquire() as conn:
        for attr in attributions:
            await conn.execute(
                """
                INSERT INTO hairgpt_conversions
                    (session_id, shopify_order_id, order_number, order_total,
                     hairgpt_revenue, hairgpt_items, total_items, order_created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (shopify_order_id) DO UPDATE SET
                    hairgpt_revenue = EXCLUDED.hairgpt_revenue,
                    hairgpt_items = EXCLUDED.hairgpt_items,
                    reconciled_at = NOW()
                """,
                attr["session_id"],
                attr["shopify_order_id"],
                attr["order_number"],
                attr["order_total"],
                attr["hairgpt_revenue"],
                attr["hairgpt_items"],
                attr["total_items"],
                attr["order_created_at"],
            )
    print(f"Upserted {len(attributions)} conversion records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1, help="Look back N days (default: 1)")
    args = parser.parse_args()
    asyncio.run(reconcile(args.days))
