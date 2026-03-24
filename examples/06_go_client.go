// Example 6: Async Go client
//
// Demonstrates the "hardware interrupt" pattern in Go:
//   - Main goroutine does periodic work (simulated sensor reads)
//   - HTTP server goroutine listens for interrupt webhooks
//   - On interrupt → goroutine handles fetch + ACK concurrently
//   - Main work is NEVER blocked by interrupt handling
//
// Usage:
//   export HKN_API=http://localhost:8042
//   export PASSKEY=test123
//   go run 06_go_client.go
//
// Webhook: http://localhost:9000/webhook/order

package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"
)

// ── Config ───────────────────────────────────────────────────────

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

var (
	hknAPI  = env("HKN_API", "http://localhost:8042")
	passkey = env("PASSKEY", "test123")
	port    = env("LISTEN_PORT", "9000")
)

// ── Types ────────────────────────────────────────────────────────

type InterruptPayload struct {
	OrderIDs []string `json:"order_ids"`
}

type OrderEntry struct {
	Key  string                 `json:"key"`
	Data map[string]interface{} `json:"data"`
}

type OrdersResponse struct {
	Orders []OrderEntry `json:"orders"`
	Count  int          `json:"count"`
}

type AckRequest struct {
	Passkey      string   `json:"passkey"`
	ReceivedKeys []string `json:"received_keys"`
}

type AckResponse struct {
	Status    string   `json:"status"`
	Cleaned   []string `json:"cleaned"`
	Remaining int      `json:"remaining"`
}

// ── Order processing ─────────────────────────────────────────────

func processOrder(key string, data map[string]interface{}) bool {
	log.Printf("  📦 Order #%s | %s (%s) | $%s",
		data["order_number"], data["customer_name"],
		data["customer_id"], data["total"])
	return true
}

// ── Interrupt handler (runs in its own goroutine) ────────────────

func handleInterrupt(orderIDs []string) {
	log.Printf("\n🔔 INTERRUPT! %d new order(s) — handler goroutine firing...", len(orderIDs))

	// Step 1: Query
	log.Println("🔍 Querying orders...")
	resp, err := http.Get(fmt.Sprintf("%s/orders?passkey=%s", hknAPI, passkey))
	if err != nil {
		log.Printf("❌ Query failed: %v", err)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	var ordersResp OrdersResponse
	json.Unmarshal(body, &ordersResp)

	if len(ordersResp.Orders) == 0 {
		log.Println("   No unread orders")
		return
	}

	log.Printf("📬 Received %d order(s):", len(ordersResp.Orders))

	// Step 2: Process each order
	var ackedKeys []string
	for _, order := range ordersResp.Orders {
		if processOrder(order.Key, order.Data) {
			ackedKeys = append(ackedKeys, order.Key)
		}
	}

	// Step 3: ACK
	if len(ackedKeys) > 0 {
		log.Printf("📤 ACK'ing %d key(s)...", len(ackedKeys))
		ackReq := AckRequest{Passkey: passkey, ReceivedKeys: ackedKeys}
		ackBody, _ := json.Marshal(ackReq)

		ackResp, err := http.Post(
			hknAPI+"/orders/ack",
			"application/json",
			bytes.NewReader(ackBody),
		)
		if err != nil {
			log.Printf("❌ ACK failed: %v", err)
			return
		}
		defer ackResp.Body.Close()

		var result AckResponse
		ackRespBody, _ := io.ReadAll(ackResp.Body)
		json.Unmarshal(ackRespBody, &result)
		log.Printf("✅ ACK result: cleaned=%d remaining=%d", len(result.Cleaned), result.Remaining)
	}

	log.Println("↩️  Handler goroutine done — main work was never blocked\n")
}

// ── Webhook server ───────────────────────────────────────────────

func webhookHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" || r.URL.Path != "/webhook/order" {
		http.NotFound(w, r)
		return
	}

	body, _ := io.ReadAll(r.Body)
	var payload InterruptPayload
	json.Unmarshal(body, &payload)

	// Respond immediately
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"received"}`))

	// Handle in separate goroutine — non-blocking
	go handleInterrupt(payload.OrderIDs)
}

// ── Main ─────────────────────────────────────────────────────────

func main() {
	fmt.Println("╔══════════════════════════════════════╗")
	fmt.Println("║  HKN POS — Go Async Client            ║")
	fmt.Println("╚══════════════════════════════════════╝")
	fmt.Printf("  HKN API:  %s\n", hknAPI)
	fmt.Printf("  Webhook:  http://localhost:%s/webhook/order\n", port)
	fmt.Println()
	fmt.Println("⚙️  Main work running (interrupt won't block it)...")
	fmt.Println()

	// Start webhook server in a goroutine
	http.HandleFunc("/webhook/order", webhookHandler)
	go func() {
		log.Fatal(http.ListenAndServe(":"+port, nil))
	}()

	// Main work loop — runs forever, never blocked by interrupts
	tasks := []string{"reading sensors", "processing data", "updating display", "checking battery"}
	tick := 0
	for {
		tick++
		task := tasks[tick%len(tasks)]
		fmt.Printf("  ⚙️  [tick %d] Main work: %s...\r", tick, task)
		time.Sleep(1 * time.Second)
	}
}
