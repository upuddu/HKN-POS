# HKN POS

Order processing system for Purdue's Eta Kappa Nu (HKN) chapter. Monitors a shared IMAP mailbox for TooCOOL order confirmation emails, extracts structured data from the attached PDF receipts, and exposes the results through a REST API with a webhook-based interrupt/ACK protocol.

Built to replace the manual workflow of checking email, opening PDFs, and copying reload amounts into a spreadsheet. The server watches the inbox in real time using IMAP IDLE (no polling), parses each PDF the moment it arrives, and pushes an interrupt to whatever downstream system needs the data.

---

## How It Works

```
  Purdue IMAP Mailbox                HKN POS Server                  Your App
  ───────────────────      ───────────────────────────────      ─────────────────
                           
  New email arrives        IMAP IDLE wakes up
  with PDF attachment  --> Download + parse PDF
                           Store order in SQLite
                           Fire webhook interrupt  ----------> POST /webhook/order
                                                               
                           GET  /orders?passkey=...  <--------  Query for full data
                           POST /orders/ack          <--------  ACK received keys
                           
                           (if no ACK within 30s,
                            re-fire the interrupt)
```

The interrupt/ACK handshake guarantees delivery. If the downstream system crashes or misses the interrupt, the server keeps retrying until every order is acknowledged and cleaned from the queue.

---

## Project Structure

```
hkn_pos/
    main.py            Entry point, CLI argument handling, server startup
    api.py             FastAPI endpoints: GET /orders, POST /orders/ack, GET /health
    config.py          Environment-based configuration (IMAP, API, webhook)
    email_monitor.py   IMAP IDLE monitor, PDF attachment extraction
    events.py          Lightweight publish/subscribe event bus
    models.py          OrderData and OrderItem dataclasses
    pdf_parser.py      Regex-based PDF text extraction (pdfplumber)
    storage.py         SQLite-backed order store with UUID keys
    webhook.py         Outbound webhook client with retry logic
    comm_log.py        Communication audit log with automatic rotation
examples/              Client implementations in 7 languages (see examples/README.md)
hknctl                 Bash control script for starting/stopping the server
setup.sh               One-shot environment setup
Dockerfile             Multi-stage container build
docker-compose.yml     Production deployment config
```

---

## Requirements

- Python 3.10 or later
- A Purdue (Office 365) email account with an app password
- That is literally it

---

## Setup

```bash
git clone https://github.com/upuddu/HKN-POS.git
cd HKN-POS
bash setup.sh
```

The setup script creates a virtual environment, installs dependencies, initializes the SQLite database, copies `.env.example` to `.env`, and runs the test suite. After it finishes, edit `.env` with your credentials:

```bash
EMAIL_ADDRESS=your-purdue-email@purdue.edu
EMAIL_PASSWORD=your-app-password
API_PASSKEY=some-shared-secret
WEBHOOK_URL=http://your-server:9000/webhook/order
```

---

## Usage

### Start the server

```bash
./hknctl start          # background, logs to hkn_pos.log
./hknctl start -v       # verbose (debug logging)
```

This starts the FastAPI server on port 8042 and, if email credentials are present, launches the IMAP IDLE monitor in a background thread.

### Parse a single PDF without the server

```bash
hkn-pos --parse-pdf "Order 131376.pdf" --json
```

### Control commands

```bash
./hknctl status         # server PID, health check, DB summary
./hknctl stop           # graceful shutdown
./hknctl restart        # stop + start
./hknctl db             # print all pending orders
./hknctl logs           # last 20 communication log entries
./hknctl logs --all     # full audit trail
./hknctl logs --clear   # wipe the comm log
./hknctl parse file.pdf # parse and store a PDF
```

---

## API

All endpoints require a `passkey` parameter matching the `API_PASSKEY` environment variable.

### `GET /orders?passkey=...`

Returns all unread orders.

```json
{
  "orders": [
    {
      "key": "a1b2c3d4...",
      "data": {
        "order_number": "131376",
        "customer_name": "Elijah Luke Jorgensen",
        "customer_id": "jorgenel",
        "reload_amount": "153.00",
        "total": "1.10",
        "store_code": "02207",
        "store_name": "ETA KAPPA NU LOUNGE SALES",
        "paid": true
      }
    }
  ],
  "count": 1
}
```

### `POST /orders/ack`

Acknowledge and remove orders from the queue.

```json
{
  "passkey": "your-secret",
  "received_keys": ["a1b2c3d4..."]
}
```

### `GET /health`

No auth required. Returns server status and unread order count.

---

## Docker

```bash
cp .env.example .env    # fill in credentials
docker compose up -d    # start
docker compose logs -f  # watch
docker compose down     # stop
```

The container persists the SQLite database and downloaded PDFs across restarts using named volumes.

---

## Client Examples

The `examples/` directory has working client implementations in Shell, Python (sync, async, polling), JavaScript, Go, and Rust. Each one demonstrates the interrupt/ACK protocol. See [`examples/README.md`](examples/README.md) for details and a quick-start guide.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EMAIL_ADDRESS` | | Purdue email for IMAP monitoring |
| `EMAIL_PASSWORD` | | App password (not your main password) |
| `IMAP_HOST` | `outlook.office365.com` | IMAP server |
| `IMAP_PORT` | `993` | IMAP port |
| `TARGET_SENDER` | `BOSOFinance@Purdue.edu` | Filter emails by sender |
| `TARGET_SUBJECT` | `TooCOOL Order Confirmation` | Filter emails by subject |
| `API_PORT` | `8042` | FastAPI server port |
| `API_PASSKEY` | | Shared secret for API auth |
| `WEBHOOK_URL` | | Downstream server interrupt endpoint |
| `ACK_TIMEOUT` | `30` | Seconds before retrying unACK'd interrupts |
| `DB_PATH` | `hkn_pos.db` | SQLite database file |
| `DOWNLOAD_DIR` | `downloads` | Where to save PDF attachments |

---

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -q
```

---

## License

Internal tool for Purdue HKN. Not licensed for external use.
