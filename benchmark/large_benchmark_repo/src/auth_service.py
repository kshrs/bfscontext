"""Authentication management service."""
from security import hash_token
from user_model import User

class AuthService:
    def __init__(self):
        self.session_store = {}

    def authenticate_user(self, token: str) -> bool:
        hashed = hash_token(token)
        return hashed in self.session_store

    def register_session(self, user: User, token: str) -> None:
        self.session_store[hash_token(token)] = user
