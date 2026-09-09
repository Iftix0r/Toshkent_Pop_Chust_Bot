import json
from datetime import datetime, timezone
from pathlib import Path

USERS_FILE = Path(__file__).parent / "users.json"

_lock_data: dict[str, dict] = {}


def _load() -> dict[str, dict]:
    if not USERS_FILE.exists():
        return {}
    with USERS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict[str, dict]) -> None:
    with USERS_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register_user(user_id: int, full_name: str, username: str | None) -> bool:
    """Save the user if not seen before. Returns True if this is a new user."""
    data = _load()
    key = str(user_id)
    if key in data:
        return False

    data[key] = {
        "full_name": full_name,
        "username": username,
        "joined_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(data)
    return True


def users_count() -> int:
    return len(_load())
