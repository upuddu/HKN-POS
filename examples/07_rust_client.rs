// Example 7: Async Rust client
//
// Demonstrates the "hardware interrupt" pattern in Rust:
//   - Main task does periodic work on a tokio interval
//   - Axum HTTP server listens for interrupt webhooks
//   - On interrupt → spawns a tokio task for fetch + ACK
//   - Main work is NEVER blocked by interrupt handling
//
// Setup:
//   cd examples/07_rust_client
//   cargo run
//
// This file is the instructions — see 07_rust_client/ for the actual project.

// The Cargo project is in examples/07_rust_client/
