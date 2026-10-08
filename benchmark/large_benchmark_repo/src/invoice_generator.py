"""PDF invoice generator and formatter."""
class InvoiceGenerator:
    def generate_pdf_invoice(self, order_id: str, items: list) -> bytes:
        return b"%PDF-1.4 dummy invoice"
