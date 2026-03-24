"""Data models for parsed TooCOOL order confirmations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class OrderItem:
    """A single line-item from the order."""

    quantity: int
    description: str
    color: str = ""
    size: str = ""
    unit_price: Decimal = Decimal("0.00")
    shipping: Decimal = Decimal("0.00")
    sales_tax: Decimal = Decimal("0.00")
    price: Decimal = Decimal("0.00")


@dataclass
class OrderData:
    """Fully parsed order confirmation."""

    # Order metadata
    order_number: str = ""
    order_date: str = ""
    customer_id: str = ""
    customer_name: str = ""

    # Shipping
    ship_to_address: str = ""

    # Store / source verification
    store_code: str = ""        # e.g. "02207"
    store_name: str = ""        # e.g. "ETA KAPPA NU LOUNGE SALES"
    pickup_location: str = ""   # e.g. "BHEE 138 HKN Lounge"

    # Items
    items: list[OrderItem] = field(default_factory=list)

    # Reload amount — the key value: "$X.XX Eta Kappa Nu Reload"
    reload_amount: Decimal = Decimal("0.00")

    # Totals
    subtotal: Decimal = Decimal("0.00")
    shipping_total: Decimal = Decimal("0.00")
    sales_tax_total: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")

    # Status
    paid: bool = False

    # Source PDF path (if available)
    source_pdf: str = ""

    def summary(self) -> str:
        """Human-readable one-liner."""
        return (
            f"Order #{self.order_number} | {self.customer_name} | "
            f"Reload: ${self.reload_amount} | Total: ${self.total} | "
            f"Store: ({self.store_code}) {self.store_name}"
        )
