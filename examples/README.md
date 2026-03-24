# Example Clients for HKN POS API

This directory contains multiple client implementations showing how to properly
interact with the HKN POS order notification system.

## How the Protocol Works

```
┌─────────────────────────────────────────────────────────────────┐
│  1. HKN POS server sends INTERRUPT to your webhook URL         │
│     POST /webhook/order  {"order_ids": ["abc123", "def456"]}   │
│                                                                 │
│  2. Your client queries back with the shared passkey            │
│     GET /orders?passkey=YOUR_SECRET                             │
│                                                                 │
│  3. Your client ACKs the received order keys                    │
│     POST /orders/ack {"passkey":"...","received_keys":["..."]}  │
│                                                                 │
│  4. If you don't ACK within 30s, the interrupt re-fires         │
└─────────────────────────────────────────────────────────────────┘
```

## Examples

| Example | Language | Async Pattern | Best For |
|---------|----------|---------------|----------|
| `01_curl_client.sh` | Shell | — | Quick testing, cron jobs |
| `02_flask_client.py` | Python | `threading.Thread` | Simple servers |
| `03_async_client.py` | Python | `asyncio` / `BackgroundTasks` | High-perf Python servers |
| `04_polling_client.py` | Python | Periodic loop | Firewalled environments |
| `05_node_client.js` | JavaScript | `setInterval` + `async/await` | Node.js apps |
| `06_go_client.go` | Go | `go func()` goroutine | Go microservices |
| `07_rust_client/` | Rust | `tokio::spawn` task | Systems / embedded |

### The "Hardware Interrupt" Pattern

Examples 05–07 demonstrate that **main work continues unblocked** while
the interrupt handler runs asynchronously — just like a hardware interrupt:

```
Main loop:  ⚙️ tick 1 ... ⚙️ tick 2 ... ⚙️ tick 3 ...
                                   ↑
                          🔔 INTERRUPT fires
                          🔍 Query (async)
                          📤 ACK (async)
                          ↩️ Done
                                   ↓
            ... ⚙️ tick 4 ... ⚙️ tick 5 ...  (never blocked)
```

## Quick Test

In **three terminals**:

```bash
# Terminal 1 — Start HKN POS server
cd /path/to/HKN_Pos
API_PASSKEY=test123 WEBHOOK_URL=http://localhost:9000/webhook/order \
  python -m hkn_pos.main --serve

# Terminal 2 — Start an example client
cd /path/to/HKN_Pos/examples
python 02_flask_client.py

# Terminal 3 — Trigger an order
cd /path/to/HKN_Pos
python -m hkn_pos.main --parse-pdf "Order 131376 Elijah Luke Jorgensen 153 TooCOOL.pdf"
```

Watch Terminal 2 — it will receive the interrupt, query, and ACK automatically.
