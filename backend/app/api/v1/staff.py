from fastapi import APIRouter

from app.api.deps import ChiefUser, StaffServiceDep
from app.schemas.staff import StaffDoctorIn, StaffDoctorOut, StaffDoctorPatch

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/doctors", response_model=list[StaffDoctorOut], summary="Врачи с нагрузкой")
async def doctors(user: ChiefUser, service: StaffServiceDep) -> list[StaffDoctorOut]:
    return [StaffDoctorOut.build(v) for v in service.doctors()]


@router.post("/doctors", response_model=StaffDoctorOut, summary="Добавить врача")
async def create_doctor(
    body: StaffDoctorIn, user: ChiefUser, service: StaffServiceDep
) -> StaffDoctorOut:
    return StaffDoctorOut.build(service.create(user, **body.model_dump()))


@router.patch(
    "/doctors/{doctor_id}", response_model=StaffDoctorOut, summary="Изменить или отключить врача"
)
async def update_doctor(
    doctor_id: str, body: StaffDoctorPatch, user: ChiefUser, service: StaffServiceDep
) -> StaffDoctorOut:
    return StaffDoctorOut.build(service.update(user, doctor_id, **body.model_dump()))
