#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Example 1: Shell / curl client
#
# This is the simplest possible client. It starts a tiny HTTP
# listener (using Python's built-in http.server), waits for an
# interrupt from the HKN POS server, then queries and ACKs using
# curl.
#
# Usage:
#   export HKN_API=http://localhost:8042
#   export PASSKEY=test123
#   bash 01_curl_client.sh
#
# Requires: bash, curl, python3 (for the webhook listener)
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

HKN_API="${HKN_API:-http://localhost:8042}"
PASSKEY="${PASSKEY:-test123}"
LISTEN_PORT="${LISTEN_PORT:-9000}"

echo "╔══════════════════════════════════════╗"
echo "║  HKN POS — Curl Client Example       ║"
echo "╚══════════════════════════════════════╝"
echo "  API:    $HKN_API"
echo "  Listen: http://localhost:$LISTEN_PORT/webhook/order"
echo ""

# ── Function: query and ACK ──────────────────────────────────────

query_and_ack() {
    echo "📨  Interrupt received! Querying orders..."

    # Step 1: GET all unread orders
    local response
    response=$(curl -s "$HKN_API/orders?passkey=$PASSKEY")

    local count
    count=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['count'])" 2>/dev/null || echo "0")

    echo "📦  Received $count order(s)"

    if [ "$count" = "0" ]; then
        echo "   (nothing to ACK)"
        return
    fi

    # Pretty-print orders
    echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for o in data['orders']:
    d = o['data']
    print(f'   #{d[\"order_number\"]} | {d[\"customer_name\"]} ({d[\"customer_id\"]}) | \${d[\"total\"]}')
" 2>/dev/null

    # Step 2: Extract all keys
    local keys
    keys=$(echo "$response" | python3 -c "
import sys, json
data = json.load(sys.stdin)
keys = [o['key'] for o in data['orders']]
print(json.dumps(keys))
" 2>/dev/null)

    # Step 3: ACK all keys
    echo "📤  Sending ACK for keys: $keys"
    local ack_response
    ack_response=$(curl -s -X POST "$HKN_API/orders/ack" \
        -H "Content-Type: application/json" \
        -d "{\"passkey\":\"$PASSKEY\",\"received_keys\":$keys}")

    echo "✅  ACK response: $ack_response"
    echo ""
}

# ── Webhook listener ─────────────────────────────────────────────
# We use a tiny Python HTTP server to receive the POST interrupt

echo "🎧  Listening for interrupts on port $LISTEN_PORT..."
echo "   (Press Ctrl+C to stop)"
echo ""

python3 -c "
import http.server
import json
import subprocess
import sys

class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/webhook/order':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode()
            data = json.loads(body) if body else {}

            print(f'\\n🔔  INTERRUPT received: {json.dumps(data)}')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{\"status\":\"received\"}')

            # Trigger the query-and-ACK in a subprocess
            subprocess.Popen(
                ['bash', '-c', 'source $0 && query_and_ack', sys.argv[1]],
                env={
                    **dict(__import__('os').environ),
                    'HKN_API': '$HKN_API',
                    'PASSKEY': '$PASSKEY',
                }
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress default logging

server = http.server.HTTPServer(('0.0.0.0', $LISTEN_PORT), WebhookHandler)
try:
    server.serve_forever()
except KeyboardInterrupt:
    print('\\nStopped.')
" "$0"
