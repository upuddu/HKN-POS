#!/usr/bin/env node
/**
 * Example 5: Async JavaScript (Node.js) client
 *
 * Demonstrates the "hardware interrupt" pattern:
 *   - Main loop does periodic work (simulated sensor reads)
 *   - HTTP server listens for interrupt webhooks
 *   - On interrupt → async fetch + ACK without blocking main loop
 *
 * Usage:
 *   export HKN_API=http://localhost:8042
 *   export PASSKEY=test123
 *   node 05_node_client.js
 *
 * Webhook: http://localhost:9000/webhook/order
 */

const http = require("http");
const https = require("https");

// ── Config ───────────────────────────────────────────────────────
const HKN_API = process.env.HKN_API || "http://localhost:8042";
const PASSKEY = process.env.PASSKEY || "test123";
const PORT = parseInt(process.env.LISTEN_PORT || "9000", 10);

// ── HTTP helpers (no dependencies) ───────────────────────────────
function httpRequest(method, url, body = null) {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const opts = {
      method,
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname + parsed.search,
      headers: body ? { "Content-Type": "application/json" } : {},
    };
    const req = http.request(opts, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try { resolve({ status: res.statusCode, data: JSON.parse(data) }); }
        catch { resolve({ status: res.statusCode, data }); }
      });
    });
    req.on("error", reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

// ── Order processing (your business logic goes here) ─────────────
function processOrder(key, data) {
  console.log(
    `  📦 Order #${data.order_number} | ${data.customer_name} (${data.customer_id}) | $${data.total}`
  );
  return true;
}

// ── Interrupt handler ────────────────────────────────────────────
async function handleInterrupt(orderIds) {
  console.log(`\n🔔 INTERRUPT! ${orderIds.length} new order(s) — handler firing...`);

  try {
    // Query
    console.log("🔍 Querying orders...");
    const queryRes = await httpRequest("GET", `${HKN_API}/orders?passkey=${PASSKEY}`);
    const orders = queryRes.data.orders || [];

    if (orders.length === 0) {
      console.log("   No unread orders");
      return;
    }

    console.log(`📬 Received ${orders.length} order(s):`);

    // Process each
    const ackedKeys = [];
    for (const order of orders) {
      if (processOrder(order.key, order.data)) {
        ackedKeys.push(order.key);
      }
    }

    // ACK
    if (ackedKeys.length > 0) {
      console.log(`📤 ACK'ing ${ackedKeys.length} key(s)...`);
      const ackRes = await httpRequest("POST", `${HKN_API}/orders/ack`, {
        passkey: PASSKEY,
        received_keys: ackedKeys,
      });
      console.log(`✅ ACK result: cleaned=${ackRes.data.cleaned?.length} remaining=${ackRes.data.remaining}`);
    }
  } catch (err) {
    console.error(`❌ Error in interrupt handler: ${err.message}`);
  }

  console.log("↩️  Returning to main work...\n");
}

// ── Webhook server ───────────────────────────────────────────────
const server = http.createServer((req, res) => {
  if (req.method === "POST" && req.url === "/webhook/order") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ status: "received" }));

      const payload = JSON.parse(body || "{}");
      // Fire async — don't block the response
      handleInterrupt(payload.order_ids || []);
    });
  } else {
    res.writeHead(404);
    res.end();
  }
});

// ── Main work loop (simulated) ───────────────────────────────────
let tick = 0;
function mainWork() {
  tick++;
  const tasks = ["reading sensors", "processing data", "updating display", "checking battery"];
  const task = tasks[tick % tasks.length];
  process.stdout.write(`  ⚙️  [tick ${tick}] Main work: ${task}...\r`);
}

// ── Start everything ─────────────────────────────────────────────
console.log("╔══════════════════════════════════════╗");
console.log("║  HKN POS — Node.js Async Client       ║");
console.log("╚══════════════════════════════════════╝");
console.log(`  HKN API:  ${HKN_API}`);
console.log(`  Webhook:  http://localhost:${PORT}/webhook/order`);
console.log("");
console.log("⚙️  Main work running (interrupt won't block it)...");
console.log("");

server.listen(PORT, () => {
  // Start main work loop — runs every second regardless of interrupts
  setInterval(mainWork, 1000);
});
