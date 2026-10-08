"""User and permission models."""
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class User:
    user_id: str
    email: str
    roles: List[str]
    is_active: bool = True

def is_admin_user(user: User) -> bool:
    """Checks admin role."""
    return "admin" in user.roles
