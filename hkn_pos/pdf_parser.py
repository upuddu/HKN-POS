"""PDF parser for TooCOOL order confirmation PDFs."""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from hkn_pos.models import OrderData, OrderItem

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────
EXPECTED_STORE_TAG = "(02207) ETA KAPPA NU LOUNGE SALES"
STORE_CODE = "02207"
STORE_NAME = "ETA KAPPA NU LOUNGE SALES"

# ── Regex patterns ────────────────────────────────────────────────────
# Matches things like "131376" after "Order:" or standalone 6-digit number
RE_ORDER_NUMBER = re.compile(r"(?:Order:\s*)(\d{4,})", re.IGNORECASE)
RE_CUSTOMER_ID = re.compile(r"Customer\s+ID:\s*(\w+)", re.IGNORECASE)
RE_ORDER_DATE = re.compile(
    r"Order\s+Date:\s*(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE
)
# "$1 Eta Kappa Nu Reload" — dollar amount right before description
RE_RELOAD_AMOUNT = re.compile(
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*Eta\s+Kappa\s+Nu\s+Reload",
    re.IGNORECASE,
)
# Pickup location — may span multiple lines before "PAID"
RE_PICKUP = re.compile(r"Pick\s+Up\s+Location:\s*(.+?)PAID", re.DOTALL | re.IGNORECASE)
# Customer name: "Elijah Luke Jorgensen Order Date: ..."
RE_CUSTOMER_NAME = re.compile(r"Order:\s*\d+\n(.+?)\s*Order\s+Date:", re.DOTALL)


def _decimal(value: str) -> Decimal:
    """Safely convert a string to Decimal."""
    try:
        return Decimal(value.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return Decimal("0.00")


class PDFParser:
    """Parse a TooCOOL order confirmation PDF into an `OrderData` object."""

    def parse(self, pdf_path: str | Path) -> OrderData:
        """Parse the PDF at *pdf_path* and return structured `OrderData`.

        Raises `ValueError` if the PDF does not look like an HKN order.
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        text = self._extract_text(pdf_path)
        logger.debug("Extracted text (%d chars): %s…", len(text), text[:200])

        # ── Verify store identity ──────────────────────────────────
        if EXPECTED_STORE_TAG not in text:
            raise ValueError(
                f"PDF does not contain expected store tag '{EXPECTED_STORE_TAG}'. "
                "This doesn't look like an HKN TooCOOL order."
            )

        order = OrderData(source_pdf=str(pdf_path))
        order.store_code = STORE_CODE
        order.store_name = STORE_NAME

        # ── Order metadata ─────────────────────────────────────────
        m = RE_ORDER_NUMBER.search(text)
        if m:
            order.order_number = m.group(1)

        m = RE_ORDER_DATE.search(text)
        if m:
            order.order_date = m.group(1).strip()

        m = RE_CUSTOMER_ID.search(text)
        if m:
            order.customer_id = m.group(1).strip()

        # ── Customer name (appears after Customer ID line) ─────────
        order.customer_name = self._extract_customer_name(text)

        # ── Ship-to address ────────────────────────────────────────
        order.ship_to_address = self._extract_ship_to(text)

        # ── Reload amount ──────────────────────────────────────────
        m = RE_RELOAD_AMOUNT.search(text)
        if m:
            order.reload_amount = _decimal(m.group(1))

        # ── Pickup location ────────────────────────────────────────
        m = RE_PICKUP.search(text)
        if m:
            order.pickup_location = m.group(1).strip()

        # ── Paid status ────────────────────────────────────────────
        order.paid = "PAID" in text

        # ── Totals (last occurrence of the 4-number summary) ───────
        self._extract_totals(text, order)

        # ── Line items ─────────────────────────────────────────────
        self._extract_items(text, order)

        logger.info("Parsed order: %s", order.summary())
        return order

    # ── Private helpers ────────────────────────────────────────────────

    @staticmethod
    def _extract_text(pdf_path: Path) -> str:
        """Extract all text from the first page of the PDF."""
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            return "\n".join(pages_text)

    @staticmethod
    def _extract_customer_name(text: str) -> str:
        """Extract e.g. 'Elijah Luke Jorgensen' from the text.

        In the PDF layout, the name appears on the line right after
        'Order: NNNNN' and before 'Order Date:'.
        E.g.: "Order: 131376\\nElijah Luke Jorgensen Order Date: 15 Sep 2025"
        """
        m = RE_CUSTOMER_NAME.search(text)
        if m:
            return m.group(1).strip()
        return ""

    @staticmethod
    def _extract_ship_to(text: str) -> str:
        """Extract the ship-to address block.

        Actual layout after 'Ship To:' / 'Order: NNNNN':
            Elijah Luke Jorgensen Order Date: 15 Sep 2025
            9010 Vienna Road
            Customer ID: jorgenel
            Evansville, IN 47720
            ...
            United States Of America
        We extract lines between Order: and the table header (Quantity ...).
        """
        match = re.search(
            r"Order:\s*\d+\n(.+?)(?=Page\s+\d|Quantity)",
            text, re.DOTALL | re.IGNORECASE,
        )
        if match:
            block = match.group(1)
            # Remove "Order Date: ..." and "Customer ID: ..." metadata
            block = re.sub(r"Order\s+Date:\s*\d{1,2}\s+\w+\s+\d{4}", "", block)
            block = re.sub(r"Customer\s+ID:\s*\w+", "", block)
            # Collapse whitespace
            addr = re.sub(r"\s+", " ", block).strip()
            return addr
        return ""

    @staticmethod
    def _extract_totals(text: str, order: OrderData) -> None:
        """Extract the summary totals block.

        The PDF has a summary section at the bottom like:
            Items   Shipping   Sales Tax   Total
            1.03    0.00       0.07        1.10
        """
        # Find all groups of 4 decimals on a single line
        totals_pattern = re.compile(
            r"(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})"
        )
        matches = list(totals_pattern.finditer(text))
        if matches:
            # Use the last match — the summary totals at the bottom
            last = matches[-1]
            order.subtotal = _decimal(last.group(1))
            order.shipping_total = _decimal(last.group(2))
            order.sales_tax_total = _decimal(last.group(3))
            order.total = _decimal(last.group(4))

    @staticmethod
    def _extract_items(text: str, order: OrderData) -> None:
        """Extract line items from the order table.

        Typical line: quantity followed by a $ amount, description, then
        4 decimals (unit_price, shipping, sales_tax, price).
        """
        # Simple heuristic: find lines that start with a digit (quantity)
        # and contain decimal amounts
        item_pattern = re.compile(
            r"^(\d+)\s+\$([\d,.]+)\s+(.+?)\s+"
            r"(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})",
            re.MULTILINE,
        )
        for m in item_pattern.finditer(text):
            item = OrderItem(
                quantity=int(m.group(1)),
                description=f"${m.group(2)} {m.group(3)}".strip(),
                unit_price=_decimal(m.group(4)),
                shipping=_decimal(m.group(5)),
                sales_tax=_decimal(m.group(6)),
                price=_decimal(m.group(7)),
            )
            order.items.append(item)
