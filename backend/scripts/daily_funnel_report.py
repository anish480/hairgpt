"""Generate HairGPT conversion funnel report.

Queries chat_sessions, hairgpt_events, and hairgpt_conversions to build
an end-to-end funnel: Sessions → Routine → ATC → Purchase.

Usage:
    python daily_funnel_report.py                # outputs to stdout
    python daily_funnel_report.py -o report.html # writes HTML file
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.db import get_pool

TRACKING_BASELINE = "2026-09-01T07:30:00+00:00"

FUNNEL_QUERY = """
SELECT
    TO_CHAR(date_trunc('day', cs.created_at AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM-DD') as day,
    COUNT(DISTINCT cs.session_id) as sessions,
    COUNT(DISTINCT cs.session_id) FILTER (WHERE cs.routine_recommended IS NOT NULL) as routines,
    COUNT(DISTINCT e.session_id) as atc_sessions,
    COUNT(DISTINCT c.session_id) as purchases,
    COALESCE(SUM(DISTINCT c.hairgpt_revenue), 0) as hairgpt_revenue,
    COALESCE(SUM(DISTINCT c.order_total), 0) as total_order_revenue
FROM chat_sessions cs
LEFT JOIN (
    SELECT DISTINCT session_id FROM hairgpt_events WHERE event = 'add_to_cart'
) e ON e.session_id = cs.session_id
LEFT JOIN hairgpt_conversions c ON c.session_id = cs.session_id
WHERE cs.created_at >= $1::timestamptz
GROUP BY 1
ORDER BY 1 DESC
"""

WEEKLY_FUNNEL_QUERY = """
SELECT
    TO_CHAR(date_trunc('week', cs.created_at AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM-DD') as week,
    COUNT(DISTINCT cs.session_id) as sessions,
    COUNT(DISTINCT cs.session_id) FILTER (WHERE cs.routine_recommended IS NOT NULL) as routines,
    COUNT(DISTINCT e.session_id) as atc_sessions,
    COUNT(DISTINCT c.session_id) as purchases,
    COALESCE(SUM(DISTINCT c.hairgpt_revenue), 0) as hairgpt_revenue
FROM chat_sessions cs
LEFT JOIN (
    SELECT DISTINCT session_id FROM hairgpt_events WHERE event = 'add_to_cart'
) e ON e.session_id = cs.session_id
LEFT JOIN hairgpt_conversions c ON c.session_id = cs.session_id
WHERE cs.created_at >= $1::timestamptz
GROUP BY 1
ORDER BY 1 DESC
"""

VERSION_FUNNEL_QUERY = """
SELECT
    COALESCE(cs.prompt_version, 'untagged') as version,
    COUNT(DISTINCT cs.session_id) as sessions,
    COUNT(DISTINCT cs.session_id) FILTER (WHERE cs.routine_recommended IS NOT NULL) as routines,
    COUNT(DISTINCT e.session_id) as atc_sessions,
    COUNT(DISTINCT c.session_id) as purchases,
    COALESCE(SUM(DISTINCT c.hairgpt_revenue), 0) as hairgpt_revenue
FROM chat_sessions cs
LEFT JOIN (
    SELECT DISTINCT session_id FROM hairgpt_events WHERE event = 'add_to_cart'
) e ON e.session_id = cs.session_id
LEFT JOIN hairgpt_conversions c ON c.session_id = cs.session_id
WHERE cs.created_at >= $1::timestamptz
GROUP BY 1
ORDER BY sessions DESC
"""

TOTALS_QUERY = """
SELECT
    COUNT(DISTINCT cs.session_id) as sessions,
    COUNT(DISTINCT cs.session_id) FILTER (WHERE cs.routine_recommended IS NOT NULL) as routines,
    COUNT(DISTINCT e.session_id) as atc_sessions,
    COUNT(DISTINCT c.session_id) as purchases,
    COALESCE(SUM(DISTINCT c.hairgpt_revenue), 0) as hairgpt_revenue,
    COALESCE(SUM(DISTINCT c.order_total), 0) as total_order_revenue
FROM chat_sessions cs
LEFT JOIN (
    SELECT DISTINCT session_id FROM hairgpt_events WHERE event = 'add_to_cart'
) e ON e.session_id = cs.session_id
LEFT JOIN hairgpt_conversions c ON c.session_id = cs.session_id
WHERE cs.created_at >= $1::timestamptz
"""

TOP_PRODUCTS_QUERY = """
SELECT
    payload->>'product_handle' as product,
    COUNT(*) as atc_count,
    COUNT(DISTINCT session_id) as unique_sessions
FROM hairgpt_events
WHERE event = 'add_to_cart'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10
"""


def pct(num, denom):
    if not denom:
        return "—"
    return f"{num / denom * 100:.1f}%"


def fmt_currency(val):
    if not val:
        return "₹0"
    return f"₹{val:,.0f}"


async def generate_report() -> str:
    baseline = datetime.fromisoformat(TRACKING_BASELINE)
    pool = await get_pool()
    async with pool.acquire() as conn:
        totals = await conn.fetchrow(TOTALS_QUERY, baseline)
        daily = await conn.fetch(FUNNEL_QUERY, baseline)
        weekly = await conn.fetch(WEEKLY_FUNNEL_QUERY, baseline)
        by_version = await conn.fetch(VERSION_FUNNEL_QUERY, baseline)
        top_products = await conn.fetch(TOP_PRODUCTS_QUERY)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    t = dict(totals)

    html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>HairGPT Funnel Report — {now}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; color: #2d2d2d; background: #fafafa; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .subtitle {{ color: #888; font-size: 0.85rem; margin-bottom: 30px; }}
  .funnel {{ display: flex; gap: 12px; margin: 24px 0 32px; flex-wrap: wrap; }}
  .funnel-step {{ flex: 1; min-width: 140px; background: #fff; border-radius: 12px; padding: 16px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
  .funnel-step .num {{ font-size: 1.8rem; font-weight: 700; color: #2d2d2d; }}
  .funnel-step .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; }}
  .funnel-step .rate {{ font-size: 0.8rem; color: #7ed2c1; font-weight: 600; margin-top: 6px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0 32px; font-size: 0.85rem; }}
  th {{ text-align: left; padding: 8px 12px; border-bottom: 2px solid #e0e0e0; font-weight: 600; color: #555; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }}
  tr:hover td {{ background: #f8f8f8; }}
  .right {{ text-align: right; }}
  h2 {{ font-size: 1.1rem; margin-top: 36px; margin-bottom: 8px; }}
  .note {{ font-size: 0.8rem; color: #aaa; margin-top: 40px; }}
</style>
</head><body>
<h1>HairGPT Conversion Funnel</h1>
<p class="subtitle">Generated {now}</p>

<div class="funnel">
  <div class="funnel-step">
    <div class="num">{t['sessions']:,}</div>
    <div class="label">Sessions</div>
    <div class="rate">100%</div>
  </div>
  <div class="funnel-step">
    <div class="num">{t['routines']:,}</div>
    <div class="label">Routines</div>
    <div class="rate">{pct(t['routines'], t['sessions'])}</div>
  </div>
  <div class="funnel-step">
    <div class="num">{t['atc_sessions']:,}</div>
    <div class="label">Add to Cart</div>
    <div class="rate">{pct(t['atc_sessions'], t['routines'])}</div>
  </div>
  <div class="funnel-step">
    <div class="num">{t['purchases']:,}</div>
    <div class="label">Purchases</div>
    <div class="rate">{pct(t['purchases'], t['atc_sessions'])}</div>
  </div>
</div>

<div class="funnel" style="margin-top:-16px;">
  <div class="funnel-step">
    <div class="num">{fmt_currency(t['hairgpt_revenue'])}</div>
    <div class="label">Attributed Revenue</div>
  </div>
  <div class="funnel-step">
    <div class="num">{fmt_currency(t['total_order_revenue'])}</div>
    <div class="label">Total Order Value</div>
  </div>
</div>

<h2>Weekly Breakdown</h2>
<table>
<tr><th>Week</th><th class="right">Sessions</th><th class="right">Routines</th><th class="right">ATC</th><th class="right">Purchases</th><th class="right">Revenue</th></tr>
"""

    for row in weekly:
        r = dict(row)
        html += f'<tr><td>{r["week"]}</td><td class="right">{r["sessions"]:,}</td><td class="right">{r["routines"]:,}</td><td class="right">{r["atc_sessions"]:,}</td><td class="right">{r["purchases"]:,}</td><td class="right">{fmt_currency(r["hairgpt_revenue"])}</td></tr>\n'

    html += """</table>

<h2>Daily Breakdown (last 14 days)</h2>
<table>
<tr><th>Date</th><th class="right">Sessions</th><th class="right">Routines</th><th class="right">ATC</th><th class="right">Purchases</th><th class="right">Revenue</th></tr>
"""

    for row in daily[:14]:
        r = dict(row)
        html += f'<tr><td>{r["day"]}</td><td class="right">{r["sessions"]:,}</td><td class="right">{r["routines"]:,}</td><td class="right">{r["atc_sessions"]:,}</td><td class="right">{r["purchases"]:,}</td><td class="right">{fmt_currency(r["hairgpt_revenue"])}</td></tr>\n'

    html += """</table>

<h2>By Prompt Version</h2>
<table>
<tr><th>Version</th><th class="right">Sessions</th><th class="right">Routines</th><th class="right">ATC</th><th class="right">Purchases</th><th class="right">Revenue</th></tr>
"""

    for row in by_version:
        r = dict(row)
        html += f'<tr><td><code>{r["version"]}</code></td><td class="right">{r["sessions"]:,}</td><td class="right">{r["routines"]:,}</td><td class="right">{r["atc_sessions"]:,}</td><td class="right">{r["purchases"]:,}</td><td class="right">{fmt_currency(r["hairgpt_revenue"])}</td></tr>\n'

    html += """</table>

<h2>Top Products (Add to Cart)</h2>
<table>
<tr><th>Product</th><th class="right">ATC Count</th><th class="right">Unique Sessions</th></tr>
"""

    for row in top_products:
        r = dict(row)
        html += f'<tr><td>{r["product"]}</td><td class="right">{r["atc_count"]:,}</td><td class="right">{r["unique_sessions"]:,}</td></tr>\n'

    html += f"""</table>

<p class="note">Funnel baseline: {TRACKING_BASELINE}. Only sessions from this date onward are included — earlier sessions had no ATC/purchase tracking.</p>
</body></html>"""

    return html


async def main(output: str | None):
    report = await generate_report()
    if output:
        with open(output, "w") as f:
            f.write(report)
        print(f"Report written to {output}")
    else:
        print(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", help="Output HTML file path")
    args = parser.parse_args()
    asyncio.run(main(args.output))
