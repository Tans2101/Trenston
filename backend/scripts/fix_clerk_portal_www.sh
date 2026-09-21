#!/usr/bin/env bash
# Point Clerk Paths + redirects at www so Google OAuth never lands on accounts.*
# (accounts.trenston.com is Cloudflare-challenged → "Unable to complete action").
#
# CRITICAL: URL must include /v1. Without it Clerk returns plain: 404 page not found
#   Wrong: https://api.clerk.com/account_portal
#   Right: https://api.clerk.com/v1/account_portal
set -euo pipefail

KEY="${CLERK_SECRET_KEY:-}"
if [[ -z "$KEY" ]]; then
  echo "Paste your sk_live_… key, then press Enter (rotate it after — never commit it):"
  read -r KEY
fi
KEY="${KEY#"${KEY%%[![:space:]]*}"}"
KEY="${KEY%"${KEY##*[![:space:]]}"}"
if [[ ! "$KEY" =~ ^sk_(live|test)_ ]]; then
  echo "Expected a Clerk secret key starting with sk_live_ or sk_test_" >&2
  exit 1
fi

AUTH=(-H "Authorization: Bearer ${KEY}" -H "Content-Type: application/json")
WWW='https://www.trenston.com'
LOGIN="${WWW}/login"
SIGNUP="${WWW}/sign-up"
APP="${WWW}/app"

echo "PATCH /v1/account_portal …"
curl -sS -X PATCH 'https://api.clerk.com/v1/account_portal' "${AUTH[@]}" -d "{
  \"home_url\": \"${WWW}\",
  \"after_sign_in_url\": \"${APP}\",
  \"after_sign_up_url\": \"${APP}\",
  \"after_sign_out_all_url\": \"${LOGIN}\",
  \"after_sign_out_one_url\": \"${LOGIN}\",
  \"logo_link_url\": \"${WWW}\"
}"
echo
echo

echo "PATCH /v1/display_config (Paths) …"
curl -sS -X PATCH 'https://api.clerk.com/v1/display_config' "${AUTH[@]}" -d "{
  \"home_url\": \"${WWW}\",
  \"sign_in_url\": \"${LOGIN}\",
  \"sign_up_url\": \"${SIGNUP}\",
  \"after_sign_in_url\": \"${APP}\",
  \"after_sign_up_url\": \"${APP}\",
  \"after_sign_out_all_url\": \"${LOGIN}\",
  \"after_sign_out_one_url\": \"${LOGIN}\",
  \"logo_link_url\": \"${WWW}\"
}"
echo
echo

echo "Public Paths (must be www, not accounts.*)…"
curl -sS 'https://clerk.trenston.com/v1/environment' | python3 -c "
import json,sys
dc=json.load(sys.stdin).get('display_config') or {}
for k in ('sign_in_url','sign_up_url','after_sign_in_url','after_sign_up_url','after_sign_out_all_url'):
    print(f'{k}: {dc.get(k)}')
still=any('accounts.' in str(dc.get(k) or '') for k in ('sign_in_url','sign_up_url','after_sign_out_all_url'))
if still:
    print()
    print('STILL on accounts.* — in Clerk Dashboard → Account Portal → Disable Account Portal')
    print('(Trenston already hosts /login and /sign-up on www).')
    sys.exit(2)
print()
print('OK — Paths on www.')
"
