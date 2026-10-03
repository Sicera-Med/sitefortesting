from ulid import ULID


def new_id(prefix: str) -> str:
    """ULID с префиксом сущности: st_01J..., dc_01J... (сортируются по времени)."""
    return f"{prefix}_{ULID()}"
