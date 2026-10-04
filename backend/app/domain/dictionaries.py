"""Справочники: код → русская подпись. Используются для валидации и отдаются фронту."""

from app.domain.enums import RecommendationType, StudyType

RECOMMENDATION_TYPES: dict[str, str] = {
    RecommendationType.REPEAT_APPOINTMENT: "Повторный приём",
    RecommendationType.SPECIALIST_CONSULT: "Консультация специалиста",
    RecommendationType.ADDITIONAL_RESEARCH: "Дополнительное исследование",
    RecommendationType.URGENT_HOSPITALIZATION: "Экстренная госпитализация",
    RecommendationType.NO_PATHOLOGY: "Патологии не выявлено",
}

STUDY_TYPES: dict[str, str] = {
    StudyType.XRAY: "Рентгенография",
    StudyType.CT: "КТ",
    StudyType.MRI: "МРТ",
    StudyType.ULTRASOUND: "УЗИ",
    StudyType.MAMMOGRAPHY: "Маммография",
}

BODY_REGIONS: dict[str, str] = {
    "chest": "Органы грудной клетки",
    "head": "Головной мозг",
    "spine": "Позвоночник",
    "abdomen": "Органы брюшной полости",
    "kidneys": "Почки",
    "neck": "Щитовидная железа",
    "knee": "Коленный сустав",
    "breast": "Молочные железы",
}

SPECIALISTS: dict[str, str] = {
    "therapist": "Терапевт",
    "pulmonologist": "Пульмонолог",
    "oncologist": "Онколог",
    "cardiologist": "Кардиолог",
    "neurologist": "Невролог",
    "neurosurgeon": "Нейрохирург",
    "orthopedist": "Травматолог-ортопед",
    "gastroenterologist": "Гастроэнтеролог",
    "endocrinologist": "Эндокринолог",
    "urologist": "Уролог",
    "vascular_surgeon": "Сердечно-сосудистый (сосудистый) хирург",
    "radiotherapist": "Радиотерапевт",
}

RESEARCH_TYPES: dict[str, str] = {
    "ct": "Компьютерная томография",
    "ct_contrast": "КТ с контрастированием",
    "mri": "МРТ",
    "pet_ct": "ПЭТ-КТ",
    "ultrasound": "УЗИ",
    "mammography": "Маммография",
    "ldct": "Низкодозная КТ (НДКТ)",
    "ct_angiography": "КТ-ангиография",
    "mri_contrast": "МРТ с контрастированием",
    "adrenal_ct": "КТ надпочечников по протоколу с вымыванием или МРТ с химическим сдвигом",
    "echocardiography": "Эхокардиография (ЭхоКГ)",
    "xray": "Рентгенография",
    "biopsy": "Биопсия",
    "bronchoscopy": "Бронхоскопия",
    "lab_tests": "Лабораторные анализы",
}


def all_dictionaries() -> dict[str, list[dict[str, str]]]:
    def items(d: dict[str, str]) -> list[dict[str, str]]:
        return [{"code": str(code), "label": label} for code, label in d.items()]

    return {
        "recommendation_types": items(RECOMMENDATION_TYPES),
        "study_types": items(STUDY_TYPES),
        "body_regions": items(BODY_REGIONS),
        "specialists": items(SPECIALISTS),
        "research_types": items(RESEARCH_TYPES),
    }
