#!/usr/bin/env bash
# Mint a Shopify Admin API access token via OAuth 2.0 client_credentials grant.
# Pulls client_id + client_secret from GCP Secret Manager; prints the raw JSON
# response from Shopify (access_token + expires_in + scope) to stdout.
#
# Usage:
#   ./scripts/mint_admin_token.sh [shop_handle]
#   shop_handle defaults to "moxiebeauty-haircare" (the production store).
#
# Env overrides:
#   PROJECT_ID         GCP project (default: hairgpt-496305)
#   CLIENT_ID_SECRET   Secret name for client_id  (default: shopify-client-id)
#   CLIENT_SECRET_SECRET  Secret name for client_secret (default: shopify-client-secret)

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-hairgpt-496305}"
CLIENT_ID_SECRET="${CLIENT_ID_SECRET:-shopify-client-id}"
CLIENT_SECRET_SECRET="${CLIENT_SECRET_SECRET:-shopify-client-secret}"
SHOP="${1:-moxiebeauty-haircare}"

CLIENT_ID=$(gcloud secrets versions access latest \
  --secret="$CLIENT_ID_SECRET" --project="$PROJECT_ID")
CLIENT_SECRET=$(gcloud secrets versions access latest \
  --secret="$CLIENT_SECRET_SECRET" --project="$PROJECT_ID")

curl -sS --fail-with-body -X POST \
  "https://${SHOP}.myshopify.com/admin/oauth/access_token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}"
