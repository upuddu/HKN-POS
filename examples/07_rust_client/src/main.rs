//! Example 7: Async Rust client
//!
//! Demonstrates the "hardware interrupt" pattern in Rust:
//!   - Main task does periodic work on a tokio interval
//!   - Axum HTTP server listens for interrupt webhooks
//!   - On interrupt → spawns a tokio task for fetch + ACK
//!   - Main work is NEVER blocked by interrupt handling
//!
//! Usage:
//!   export HKN_API=http://localhost:8042
//!   export PASSKEY=test123
//!   cd examples/07_rust_client && cargo run

use axum::{extract::Json, routing::post, Router};
use serde::{Deserialize, Serialize};
use std::env;
use std::time::Duration;
use tokio::time;

// ── Config ───────────────────────────────────────────────────────

fn env_or(key: &str, fallback: &str) -> String {
    env::var(key).unwrap_or_else(|_| fallback.to_string())
}

// ── Types ────────────────────────────────────────────────────────

#[derive(Deserialize)]
struct InterruptPayload {
    order_ids: Vec<String>,
}

#[derive(Deserialize, Debug)]
struct OrderData {
    order_number: Option<String>,
    customer_name: Option<String>,
    customer_id: Option<String>,
    total: Option<String>,
}

#[derive(Deserialize, Debug)]
struct OrderEntry {
    key: String,
    data: OrderData,
}

#[derive(Deserialize, Debug)]
struct OrdersResponse {
    orders: Vec<OrderEntry>,
    count: usize,
}

#[derive(Serialize)]
struct AckRequest {
    passkey: String,
    received_keys: Vec<String>,
}

#[derive(Deserialize, Debug)]
struct AckResponse {
    status: String,
    cleaned: Vec<String>,
    remaining: usize,
}

// ── Interrupt handler ────────────────────────────────────────────

async fn handle_interrupt(order_ids: Vec<String>) {
    let api = env_or("HKN_API", "http://localhost:8042");
    let passkey = env_or("PASSKEY", "test123");

    println!(
        "\n🔔 INTERRUPT! {} new order(s) — tokio task firing...",
        order_ids.len()
    );

    let client = reqwest::Client::new();

    // Step 1: Query
    println!("🔍 Querying orders...");
    let query_url = format!("{}/orders?passkey={}", api, passkey);
    let resp = match client.get(&query_url).send().await {
        Ok(r) => r,
        Err(e) => {
            eprintln!("❌ Query failed: {}", e);
            return;
        }
    };

    let orders_resp: OrdersResponse = match resp.json().await {
        Ok(r) => r,
        Err(e) => {
            eprintln!("❌ Parse failed: {}", e);
            return;
        }
    };

    if orders_resp.orders.is_empty() {
        println!("   No unread orders");
        return;
    }

    println!("📬 Received {} order(s):", orders_resp.orders.len());

    // Step 2: Process each order
    let mut acked_keys = Vec::new();
    for order in &orders_resp.orders {
        println!(
            "  📦 Order #{} | {} ({}) | ${}",
            order.data.order_number.as_deref().unwrap_or("?"),
            order.data.customer_name.as_deref().unwrap_or("?"),
            order.data.customer_id.as_deref().unwrap_or("?"),
            order.data.total.as_deref().unwrap_or("?"),
        );
        acked_keys.push(order.key.clone());
    }

    // Step 3: ACK
    if !acked_keys.is_empty() {
        println!("📤 ACK'ing {} key(s)...", acked_keys.len());
        let ack_url = format!("{}/orders/ack", api);
        let ack_req = AckRequest {
            passkey,
            received_keys: acked_keys,
        };

        match client.post(&ack_url).json(&ack_req).send().await {
            Ok(resp) => match resp.json::<AckResponse>().await {
                Ok(result) => {
                    println!(
                        "✅ ACK result: cleaned={} remaining={}",
                        result.cleaned.len(),
                        result.remaining
                    );
                }
                Err(e) => eprintln!("❌ ACK parse error: {}", e),
            },
            Err(e) => eprintln!("❌ ACK request failed: {}", e),
        }
    }

    println!("↩️  Tokio task done — main work was never blocked\n");
}

// ── Webhook endpoint ─────────────────────────────────────────────

async fn webhook_order(
    Json(payload): Json<InterruptPayload>,
) -> axum::response::Json<serde_json::Value> {
    // Spawn a separate tokio task — non-blocking
    tokio::spawn(handle_interrupt(payload.order_ids));

    axum::response::Json(serde_json::json!({"status": "received"}))
}

// ── Main ─────────────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    let port = env_or("LISTEN_PORT", "9000");
    let api = env_or("HKN_API", "http://localhost:8042");

    println!("╔══════════════════════════════════════╗");
    println!("║  HKN POS — Rust Async Client          ║");
    println!("╚══════════════════════════════════════╝");
    println!("  HKN API:  {}", api);
    println!("  Webhook:  http://localhost:{}/webhook/order", port);
    println!();
    println!("⚙️  Main work running (interrupt won't block it)...");
    println!();

    // Start webhook server in a separate tokio task
    let app = Router::new().route("/webhook/order", post(webhook_order));
    let addr = format!("0.0.0.0:{}", port);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();

    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });

    // Main work loop — runs forever, never blocked by interrupts
    let tasks = [
        "reading sensors",
        "processing data",
        "updating display",
        "checking battery",
    ];
    let mut tick: usize = 0;
    let mut interval = time::interval(Duration::from_secs(1));

    loop {
        interval.tick().await;
        tick += 1;
        let task = tasks[tick % tasks.len()];
        print!("  ⚙️  [tick {}] Main work: {}...\r", tick, task);
    }
}
