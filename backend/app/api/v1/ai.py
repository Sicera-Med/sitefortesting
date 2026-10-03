from fastapi import APIRouter

from app.ai.contract import AIRequest
from app.api.deps import AIServiceDep, StaffUser
from app.core.ids import new_id
from app.schemas.ai import AIModelOut, AIResultOut, AITestIn, AITestOut

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/test",
    response_model=AITestOut,
    summary="Test bench: прогнать текст через AI без сохранения",
    responses={502: {"description": "AI-сервис упал или ответил не по контракту"}},
)
async def ai_test(body: AITestIn, user: StaffUser, ai: AIServiceDep) -> AITestOut:
    request = AIRequest(
        request_id=new_id("req"),
        study_id=None,
        study_type=body.study_type,
        body_region=body.body_region,
        report_text=body.report_text,
        patient_context=body.patient_context,
    )
    result, latency_ms = await ai.test_bench(user, request)
    return AITestOut(
        provider=str(ai.provider.source),
        latency_ms=latency_ms,
        result=AIResultOut.build(result),
        raw_contract=result.to_contract_json(),
    )


@router.get("/models", response_model=list[AIModelOut], summary="Модели текущего провайдера")
async def models(user: StaffUser, ai: AIServiceDep) -> list[AIModelOut]:
    return [AIModelOut(**m) for m in await ai.list_models()]
