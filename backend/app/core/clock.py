from datetime import UTC, datetime


def utcnow() -> datetime:
    """Единая точка «сейчас» — в тестах можно подменить."""
    return datetime.now(UTC)
