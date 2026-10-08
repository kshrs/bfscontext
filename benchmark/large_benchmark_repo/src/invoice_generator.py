"""PDF invoice generator and formatter."""
from typing import List, Dict, Any
from config import AppConfig
from s3_client import S3Client

class InvoiceDataError(Exception):
    pass

def format_invoice_line_item(description: str, amount: float) -> str:
    """Helper line item formatter."""
    return f"{description}: ${amount:.2f}"

def generate_invoice(order_id: str, items: List[Dict[str, Any]], s3: S3Client = None) -> Dict[str, Any]:
    """
    Generates and stores customer invoice.
    Target function for benchmarking task.
    """
    if not items:
        raise InvoiceDataError("Invoice items cannot be empty")
    
    total = sum(item.get("amount", 0.0) for item in items)
    summary_lines = [format_invoice_line_item(item["name"], item["amount"]) for item in items]
    content = "\n".join(summary_lines)
    
    client = s3 or S3Client()
    key = f"invoices/{order_id}.txt"
    client.upload_file(AppConfig.ENV, key, content.encode("utf-8"))
    
    return {
        "order_id": order_id,
        "total": total,
        "s3_key": key,
        "items_count": len(items)
    }
