"""Outbound email dispatch system."""
class EmailDispatcher:
    def send_welcome_email(self, email: str) -> bool:
        return True

    def send_receipt(self, email: str, tx_id: str, amount: float) -> bool:
        return True
