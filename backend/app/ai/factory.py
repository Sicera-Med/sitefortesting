from app.ai.base import AIProvider
from app.ai.http_provider import HttpAIProvider
from app.ai.mock_provider import MockAIProvider
from app.core.config import Settings


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.AI_PROVIDER == "http":
        return HttpAIProvider(base_url=settings.AI_BASE_URL, timeout_s=settings.AI_TIMEOUT_S)
    return MockAIProvider(latency_ms=settings.AI_MOCK_LATENCY_MS)
