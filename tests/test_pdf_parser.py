"""Tests for the PDF parser using the real sample PDF."""

from decimal import Decimal
from pathlib import Path

import pytest

from hkn_pos.pdf_parser import PDFParser

# Path to the sample PDF shipped with the repo
SAMPLE_PDF = Path(__file__).resolve().parent.parent / "Order 131376 Elijah Luke Jorgensen 153 TooCOOL.pdf"


@pytest.fixture
def parser():
    return PDFParser()


@pytest.fixture
def order(parser):
    return parser.parse(SAMPLE_PDF)


class TestPDFParser:
    """Tests against the real sample PDF."""

    def test_sample_pdf_exists(self):
        assert SAMPLE_PDF.exists(), f"Sample PDF not found at {SAMPLE_PDF}"

    def test_store_code(self, order):
        assert order.store_code == "02207"

    def test_store_name(self, order):
        assert order.store_name == "ETA KAPPA NU LOUNGE SALES"

    def test_order_number(self, order):
        assert order.order_number == "131376"

    def test_customer_id(self, order):
        assert order.customer_id == "jorgenel"

    def test_reload_amount(self, order):
        """The key value: '$1' before 'Eta Kappa Nu Reload'."""
        assert order.reload_amount == Decimal("1")

    def test_total(self, order):
        assert order.total == Decimal("1.10")

    def test_subtotal(self, order):
        assert order.subtotal == Decimal("1.03")

    def test_shipping_total(self, order):
        assert order.shipping_total == Decimal("0.00")

    def test_sales_tax(self, order):
        assert order.sales_tax_total == Decimal("0.07")

    def test_paid(self, order):
        assert order.paid is True

    def test_summary_string(self, order):
        s = order.summary()
        assert "131376" in s
        assert "1.10" in s

    def test_invalid_pdf_raises(self, parser, tmp_path):
        fake = tmp_path / "fake.pdf"
        fake.write_text("not a pdf")
        with pytest.raises(Exception):
            parser.parse(fake)

    def test_file_not_found(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.pdf")
