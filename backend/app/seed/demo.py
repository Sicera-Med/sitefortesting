"""Демо-данные (SPEC §9). Детерминированы относительно `now`: одинаковая картина
при каждом старте, даты «свежие» относительно момента запуска.

Сюжет для дашборда: 6 решений, 4 совпадают с AI. Все расхождения — при низкой
уверенности модели (< 0.7). Пациентка Кузнецова получила уведомление, но ещё
не записалась — её путь показываем вживую.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.ids import new_id
from app.core.security import hash_password
from app.domain.enums import (
    AISource,
    AppointmentStatus,
    NotificationChannel,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    Role,
    Sex,
    StudyStatus,
    StudyType,
)
from app.domain.models import (
    AIInference,
    Appointment,
    AuditEvent,
    Decision,
    Notification,
    Patient,
    RankedOption,
    Reason,
    Study,
    User,
)
from app.domain.rules import compute_accepted_ai
from app.domain.texts import notification_text
from app.store import Store

DEMO_PASSWORD = "demo"

R = RecommendationType
S = StudyStatus

# --- Персонал: (ключ, ФИО, email, роль, специальность) ---

STAFF = [
    ("head", "Смирнова Ольга Николаевна", "head@clinic.demo", Role.HEAD, None),
    ("petrov", "Петров Иван Сергеевич", "petrov@clinic.demo", Role.DOCTOR, "therapist"),
    ("sidorova", "Сидорова Анна Викторовна", "sidorova@clinic.demo", Role.DOCTOR, "pulmonologist"),
    ("kim", "Ким Алексей Дмитриевич", "kim@clinic.demo", Role.DOCTOR, "neurologist"),
    # Консультанты — к ним записываются пациенты
    ("orlov", "Орлов Дмитрий Андреевич", "orlov@clinic.demo", Role.DOCTOR, "orthopedist"),
    ("belova", "Белова Марина Юрьевна", "belova@clinic.demo", Role.DOCTOR, "oncologist"),
    ("gusev", "Гусев Павел Олегович", "gusev@clinic.demo", Role.DOCTOR, "gastroenterologist"),
    ("zakharov", "Захаров Игорь Валентинович", "zakharov@clinic.demo", Role.DOCTOR, "neurosurgeon"),
]

# --- Пациенты: (ключ, ФИО, email, дата рождения, пол, телефон) ---

PATIENTS = [
    (
        "ivanov",
        "Иванов Сергей Петрович",
        "ivanov@patient.demo",
        date(1968, 3, 14),
        Sex.M,
        "+7 900 100-00-01",
    ),
    (
        "kuznetsova",
        "Кузнецова Елена Игоревна",
        "kuznetsova@patient.demo",
        date(1975, 7, 22),
        Sex.F,
        "+7 900 100-00-02",
    ),
    (
        "popov",
        "Попов Андрей Викторович",
        "popov@patient.demo",
        date(1959, 11, 2),
        Sex.M,
        "+7 900 100-00-03",
    ),
    (
        "vasilyeva",
        "Васильева Татьяна Михайловна",
        "vasilyeva@patient.demo",
        date(1982, 5, 30),
        Sex.F,
        "+7 900 100-00-04",
    ),
    (
        "sokolov",
        "Соколов Михаил Александрович",
        "sokolov@patient.demo",
        date(1990, 1, 18),
        Sex.M,
        "+7 900 100-00-05",
    ),
    (
        "morozova",
        "Морозова Наталья Сергеевна",
        "morozova@patient.demo",
        date(1966, 9, 9),
        Sex.F,
        "+7 900 100-00-06",
    ),
    (
        "novikov",
        "Новиков Алексей Олегович",
        "novikov@patient.demo",
        date(1979, 12, 25),
        Sex.M,
        "+7 900 100-00-07",
    ),
    (
        "fedorova",
        "Фёдорова Ирина Владимировна",
        "fedorova@patient.demo",
        date(1987, 4, 3),
        Sex.F,
        "+7 900 100-00-08",
    ),
    (
        "volkov",
        "Волков Николай Дмитриевич",
        "volkov@patient.demo",
        date(1954, 6, 17),
        Sex.M,
        "+7 900 100-00-09",
    ),
    (
        "lebedeva",
        "Лебедева Ольга Андреевна",
        "lebedeva@patient.demo",
        date(1993, 8, 11),
        Sex.F,
        "+7 900 100-00-10",
    ),
]


@dataclass
class AISpec:
    recommendation: RecommendationType
    confidence: float
    reasons: list[tuple[str, str, float]]
    latency_ms: int


@dataclass
class DecisionSpec:
    chosen_type: RecommendationType
    details: dict[str, Any]
    comment: str | None = None


@dataclass
class NotificationSpec:
    channel: NotificationChannel
    read: bool = False
    # Запись: (ключ врача, через сколько дней, час) — к этому врачу на это время
    booked_with: tuple[str, int, int] | None = None


@dataclass
class StudySpec:
    patient: str
    doctor: str
    study_type: StudyType
    body_region: str
    status: StudyStatus
    days_ago: int
    report_text: str
    ai: AISpec | None = None
    decision: DecisionSpec | None = None
    notification: NotificationSpec | None = None
    extra: dict[str, Any] = field(default_factory=dict)


STUDIES: list[StudySpec] = [
    # ---------- КТ органов грудной клетки ----------
    StudySpec(
        patient="ivanov",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.DECIDED,
        days_ago=6,
        report_text=(
            "КТ органов грудной клетки без контрастирования.\n"
            "В S6 правого лёгкого определяется солидный узел размерами 8×7 мм с ровными чёткими "
            "контурами, плотностью +32 HU, без кальцинатов. Других очаговых и инфильтративных "
            "изменений не выявлено. Трахея и главные бронхи проходимы. Внутригрудные лимфоузлы "
            "не увеличены. Плевральные полости свободны.\n"
            "Заключение: солидный узел S6 правого лёгкого 8 мм. С учётом анамнеза курения "
            "(30 пачка/лет) — категория высокого риска по Fleischner."
        ),
        ai=AISpec(
            R.ADDITIONAL_RESEARCH,
            0.87,
            [
                ("nodule_8mm", "Солидный узел 8 мм в S6", 0.42),
                ("fleischner_high_risk", "Высокий риск по Fleischner", 0.31),
                ("smoking_30py", "Курение 30 пачка/лет", 0.14),
            ],
            1240,
        ),
        decision=DecisionSpec(
            R.ADDITIONAL_RESEARCH,
            {"research_type": "ct"},
            "Контрольная КТ через 3 месяца по Fleischner.",
        ),
    ),
    StudySpec(
        patient="kuznetsova",
        doctor="petrov",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NOTIFIED,
        days_ago=5,
        report_text=(
            "КТ органов грудной клетки.\n"
            "В нижней доле левого лёгкого (S9–S10) участки консолидации с воздушной "
            "бронхограммой общим размером до 54×38 мм, по периферии — зона «матового стекла». "
            "Небольшое количество жидкости в левой плевральной полости (до 8 мм). "
            "Внутригрудные лимфоузлы до 11 мм.\n"
            "Заключение: КТ-признаки левосторонней нижнедолевой пневмонии, малый левосторонний "
            "гидроторакс."
        ),
        ai=AISpec(
            R.REPEAT_APPOINTMENT,
            0.64,
            [
                ("consolidation_lll", "Консолидация в нижней доле слева", 0.38),
                ("pleural_effusion_small", "Малый гидроторакс", 0.21),
                ("no_mass", "Без признаков объёмного образования", 0.12),
            ],
            1580,
        ),
        decision=DecisionSpec(
            R.SPECIALIST_CONSULT,
            {"specialist": "pulmonologist"},
            "Распространённая пневмония с выпотом — нужен пульмонолог, а не просто контроль.",
        ),
        notification=NotificationSpec(NotificationChannel.SMS),
    ),
    StudySpec(
        patient="popov",
        doctor="petrov",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.AI_READY,
        days_ago=2,
        report_text=(
            "КТ органов грудной клетки.\n"
            "Центрилобулярная эмфизема верхних долей обоих лёгких, единичные субплевральные "
            "буллы до 12 мм. Стенки сегментарных бронхов утолщены. Очаговых и инфильтративных "
            "изменений не выявлено. Лимфоузлы средостения не увеличены.\n"
            "Заключение: КТ-картина эмфиземы лёгких, признаки хронического бронхита."
        ),
        ai=AISpec(
            R.SPECIALIST_CONSULT,
            0.78,
            [
                ("emphysema_centrilobular", "Центрилобулярная эмфизема", 0.44),
                ("bronchial_wall_thickening", "Утолщение стенок бронхов", 0.27),
                ("bullae", "Субплевральные буллы", 0.11),
            ],
            1320,
        ),
    ),
    StudySpec(
        patient="vasilyeva",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=1,
        report_text=(
            "КТ органов грудной клетки, контроль через 3 месяца после перенесённой "
            "COVID-19 пневмонии.\n"
            "Ранее описанные участки «матового стекла» в обоих лёгких полностью регрессировали. "
            "Остаточные тяжистые уплотнения в S10 справа. Очаговых и инфильтративных изменений "
            "нет. Плевральные полости свободны.\n"
            "Заключение: положительная динамика, полный регресс воспалительных изменений."
        ),
    ),
    StudySpec(
        patient="volkov",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=0,
        report_text=(
            "КТ органов грудной клетки с внутривенным контрастированием.\n"
            "В верхней доле левого лёгкого (S1+2) образование 32×28 мм с неровными "
            "спикулообразными контурами, неоднородно накапливающее контраст, с втяжением "
            "висцеральной плевры. Увеличены лимфоузлы аортопульмонального окна до 15 мм и "
            "бифуркационные до 13 мм.\n"
            "Заключение: КТ-картина периферического образования левого лёгкого, подозрительного "
            "на злокачественное (cT2aN2). Лимфаденопатия средостения."
        ),
    ),
    # ---------- Рентгенография ----------
    StudySpec(
        patient="sokolov",
        doctor="petrov",
        study_type=StudyType.XRAY,
        body_region="chest",
        status=S.NEW,
        days_ago=1,
        report_text=(
            "Рентгенография органов грудной клетки в прямой проекции.\n"
            "Лёгочные поля прозрачны, без очаговых и инфильтративных теней. Лёгочный рисунок "
            "не изменён. Корни структурны. Синусы свободны. Диафрагма с чёткими контурами. "
            "Тень сердца не расширена.\n"
            "Заключение: патологических изменений органов грудной клетки не выявлено."
        ),
    ),
    StudySpec(
        patient="morozova",
        doctor="petrov",
        study_type=StudyType.XRAY,
        body_region="knee",
        status=S.COMPLETED,
        days_ago=9,
        report_text=(
            "Рентгенография правого коленного сустава в двух проекциях.\n"
            "Суставная щель неравномерно сужена, больше в медиальном отделе. Краевые "
            "остеофиты мыщелков бедренной и большеберцовой костей. Субхондральный склероз. "
            "Заострение межмыщелковых возвышений.\n"
            "Заключение: рентгенологические признаки гонартроза II стадии по Kellgren–Lawrence."
        ),
        ai=AISpec(
            R.SPECIALIST_CONSULT,
            0.82,
            [
                ("knee_oa_kl2", "Гонартроз II ст. (Kellgren–Lawrence)", 0.47),
                ("joint_space_narrowing", "Сужение суставной щели", 0.22),
                ("osteophytes", "Краевые остеофиты", 0.13),
            ],
            980,
        ),
        decision=DecisionSpec(
            R.SPECIALIST_CONSULT,
            {"specialist": "orthopedist"},
            "Консультация ортопеда для решения о тактике лечения.",
        ),
        notification=NotificationSpec(
            NotificationChannel.SMS, read=True, booked_with=("orlov", 3, 10)
        ),
    ),
    StudySpec(
        patient="novikov",
        doctor="sidorova",
        study_type=StudyType.XRAY,
        body_region="chest",
        status=S.DECIDED,
        days_ago=3,
        report_text=(
            "Рентгенография органов грудной клетки в двух проекциях.\n"
            "Справа в нижнем лёгочном поле (S8–S9) инфильтрация лёгочной ткани средней "
            "интенсивности без чётких контуров. Правый синус свободен. Корни структурны.\n"
            "Заключение: правосторонняя нижнедолевая пневмония."
        ),
        ai=AISpec(
            R.ADDITIONAL_RESEARCH,
            0.58,
            [
                ("infiltrate_rll", "Инфильтрация в нижней доле справа", 0.36),
                ("no_effusion", "Без выпота", 0.12),
                ("ct_for_clarification", "КТ уточнит распространённость", 0.10),
            ],
            870,
        ),
        decision=DecisionSpec(
            R.REPEAT_APPOINTMENT,
            {"interval_days": 10},
            "Клинически лёгкое течение. Контрольная рентгенография после курса антибиотиков, "
            "КТ сейчас не нужна.",
        ),
    ),
    StudySpec(
        patient="fedorova",
        doctor="kim",
        study_type=StudyType.XRAY,
        body_region="spine",
        status=S.AI_READY,
        days_ago=2,
        report_text=(
            "Рентгенография поясничного отдела позвоночника в двух проекциях.\n"
            "Физиологический лордоз сглажен. Высота межпозвонковых дисков L4–L5, L5–S1 снижена. "
            "Субхондральный склероз замыкательных пластинок, краевые костные разрастания "
            "тел L4, L5. Листезов нет.\n"
            "Заключение: остеохондроз поясничного отдела позвоночника L4–S1."
        ),
        ai=AISpec(
            R.ADDITIONAL_RESEARCH,
            0.71,
            [
                ("disc_height_loss", "Снижение высоты дисков L4–S1", 0.35),
                ("mri_for_hernia", "МРТ для исключения грыжи", 0.26),
                ("osteophytes_lumbar", "Краевые разрастания тел позвонков", 0.10),
            ],
            1100,
        ),
    ),
    # ---------- МРТ ----------
    StudySpec(
        patient="popov",
        doctor="kim",
        study_type=StudyType.MRI,
        body_region="head",
        status=S.DECIDED,
        days_ago=4,
        report_text=(
            "МРТ головного мозга.\n"
            "В субкортикальном белом веществе лобных долей — единичные мелкие очаги "
            "гиперинтенсивного сигнала на T2/FLAIR до 3 мм, без перифокального отёка. "
            "Желудочки не расширены. Срединные структуры не смещены.\n"
            "Заключение: МР-картина начальных проявлений микроангиопатии (Fazekas 1)."
        ),
        ai=AISpec(
            R.REPEAT_APPOINTMENT,
            0.74,
            [
                ("fazekas_1", "Fazekas 1", 0.41),
                ("small_wm_lesions", "Единичные очаги до 3 мм", 0.24),
                ("no_mass_effect", "Нет масс-эффекта", 0.09),
            ],
            1460,
        ),
        decision=DecisionSpec(
            R.REPEAT_APPOINTMENT,
            {"interval_days": 180},
            "Контроль факторов риска, повторный осмотр через полгода.",
        ),
    ),
    StudySpec(
        patient="sokolov",
        doctor="kim",
        study_type=StudyType.MRI,
        body_region="spine",
        status=S.NOTIFIED,
        days_ago=4,
        report_text=(
            "МРТ пояснично-крестцового отдела позвоночника.\n"
            "Задняя парамедианная левосторонняя грыжа диска L5–S1 размером 7 мм с "
            "компрессией левого корешка S1. Протрузия диска L4–L5 до 2 мм. "
            "Позвоночный канал на уровне L5–S1 сужен до 10 мм.\n"
            "Заключение: грыжа диска L5–S1 с компрессией корешка S1 слева."
        ),
        ai=AISpec(
            R.SPECIALIST_CONSULT,
            0.91,
            [
                ("disc_herniation_7mm", "Грыжа L5–S1 7 мм", 0.45),
                ("root_compression_s1", "Компрессия корешка S1", 0.33),
                ("canal_stenosis", "Сужение позвоночного канала", 0.08),
            ],
            1630,
        ),
        decision=DecisionSpec(
            R.SPECIALIST_CONSULT,
            {"specialist": "neurosurgeon"},
            "Консультация нейрохирурга: решить вопрос об оперативном лечении.",
        ),
        notification=NotificationSpec(NotificationChannel.EMAIL, read=True),
    ),
    StudySpec(
        patient="lebedeva",
        doctor="petrov",
        study_type=StudyType.MRI,
        body_region="knee",
        status=S.NEW,
        days_ago=0,
        report_text=(
            "МРТ левого коленного сустава.\n"
            "В заднем роге медиального мениска линейный сигнал повышенной интенсивности, "
            "достигающий нижней суставной поверхности (Stoller 3). Передняя крестообразная "
            "связка не изменена. Умеренный выпот в верхнем завороте.\n"
            "Заключение: разрыв заднего рога медиального мениска. Синовит."
        ),
    ),
    # ---------- УЗИ ----------
    StudySpec(
        patient="vasilyeva",
        doctor="petrov",
        study_type=StudyType.ULTRASOUND,
        body_region="abdomen",
        status=S.AI_READY,
        days_ago=1,
        report_text=(
            "УЗИ органов брюшной полости.\n"
            "Печень увеличена: КВР правой доли 168 мм. Эхогенность паренхимы диффузно "
            "повышена, сосудистый рисунок обеднён, дистальное затухание сигнала. Желчный пузырь "
            "без конкрементов. Поджелудочная железа без особенностей. Селезёнка не увеличена.\n"
            "Заключение: гепатомегалия, диффузные изменения печени по типу жирового гепатоза."
        ),
        ai=AISpec(
            R.SPECIALIST_CONSULT,
            0.69,
            [
                ("hepatomegaly", "Гепатомегалия", 0.33),
                ("steatosis", "Признаки жирового гепатоза", 0.29),
                ("no_focal_lesions", "Без очаговых образований", 0.07),
            ],
            760,
        ),
    ),
    StudySpec(
        patient="fedorova",
        doctor="petrov",
        study_type=StudyType.ULTRASOUND,
        body_region="neck",
        status=S.NEW,
        days_ago=1,
        report_text=(
            "УЗИ щитовидной железы.\n"
            "Общий объём 14,2 мл. В правой доле узел 14×11×10 мм, солидный, выраженно "
            "гипоэхогенный, «выше, чем шире», с неровным контуром и точечными "
            "микрокальцинатами. Регионарные лимфоузлы не увеличены.\n"
            "Заключение: узел правой доли щитовидной железы, TI-RADS 5."
        ),
    ),
    StudySpec(
        patient="ivanov",
        doctor="petrov",
        study_type=StudyType.ULTRASOUND,
        body_region="kidneys",
        status=S.AI_FAILED,
        days_ago=2,
        report_text=(
            "УЗИ почек.\n"
            "Почки обычно расположены, размеры в норме. Паренхима 17 мм. В нижней группе "
            "чашечек левой почки гиперэхогенное включение 6 мм с акустической тенью. "
            "Чашечно-лоханочная система не расширена.\n"
            "Заключение: конкремент левой почки 6 мм без нарушения уродинамики."
        ),
    ),
]

# Дополнительные занятые слоты: (ключ пациента, ключ врача, через дней, час, минута)
EXTRA_APPOINTMENTS = [
    ("ivanov", "sidorova", 1, 10, 0),
    ("volkov", "sidorova", 1, 11, 30),
    ("popov", "sidorova", 2, 9, 0),
    ("novikov", "gusev", 1, 14, 0),
    ("lebedeva", "orlov", 2, 15, 30),
]


def _ranked(rec: RecommendationType, conf: float) -> tuple[RankedOption, ...]:
    """Остаток уверенности делим между двумя другими вариантами 2:1."""
    others = [t for t in RecommendationType if t is not rec]
    rest = 1 - conf
    return (
        RankedOption(rec, conf),
        RankedOption(others[0], round(rest * 2 / 3, 2)),
        RankedOption(others[1], round(rest / 3, 2)),
    )


def _slot(now: datetime, tz: ZoneInfo, days_ahead: int, hour: int, minute: int = 0) -> datetime:
    """Рабочий слот через N дней (выходные пропускаем вперёд до понедельника)."""
    day = now.astimezone(tz).date() + timedelta(days=days_ahead)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(UTC)


class _Seeder:
    def __init__(self, store: Store, now: datetime, tz: ZoneInfo, password_hash: str) -> None:
        self.store = store
        self.now = now
        self.tz = tz
        self.pw = password_hash
        self.users: dict[str, User] = {}
        self.patients: dict[str, Patient] = {}

    def audit(
        self, actor: User | None, action: str, study_id: str, at: datetime, **payload: Any
    ) -> None:
        self.store.append_audit(
            AuditEvent(
                id=new_id("ev"),
                actor_id=actor.id if actor else None,
                actor_role=str(actor.role) if actor else None,
                action=action,
                target_type="study",
                target_id=study_id,
                at=at,
                payload=payload,
            )
        )

    def run(self) -> None:
        for key, name, email, role, specialty in STAFF:
            self.users[key] = self.store.add_user(
                User(
                    id=new_id("usr"),
                    role=role,
                    email=email,
                    password_hash=self.pw,
                    full_name=name,
                    specialty=specialty,
                )
            )
        for key, name, email, birth, sex, phone in PATIENTS:
            user = self.store.add_user(
                User(
                    id=new_id("usr"),
                    role=Role.PATIENT,
                    email=email,
                    password_hash=self.pw,
                    full_name=name,
                )
            )
            self.patients[key] = self.store.add_patient(
                Patient(
                    id=new_id("pat"),
                    user_id=user.id,
                    full_name=name,
                    birth_date=birth,
                    sex=sex,
                    phone=phone,
                )
            )
        for spec in STUDIES:
            self.study(spec)
        for patient_key, doctor_key, days, hour, minute in EXTRA_APPOINTMENTS:
            self.store.add_appointment(
                Appointment(
                    id=new_id("ap"),
                    patient_id=self.patients[patient_key].id,
                    doctor_id=self.users[doctor_key].id,
                    scheduled_for=_slot(self.now, self.tz, days, hour, minute),
                    status=AppointmentStatus.SCHEDULED,
                    created_at=self.now - timedelta(days=1),
                )
            )

    def study(self, spec: StudySpec) -> None:
        doctor = self.users[spec.doctor]
        patient = self.patients[spec.patient]
        performed_at = self.now - timedelta(days=spec.days_ago, hours=3)
        created_at = performed_at + timedelta(hours=1)
        study = self.store.add_study(
            Study(
                id=new_id("st"),
                patient_id=patient.id,
                treating_doctor_id=doctor.id,
                study_type=spec.study_type,
                body_region=spec.body_region,
                status=spec.status,
                performed_at=performed_at,
                created_at=created_at,
                report_text=spec.report_text,
            )
        )
        self.audit(doctor, "study.created", study.id, created_at)

        t = created_at + timedelta(minutes=10)
        if spec.status is S.AI_FAILED:
            self.audit(doctor, "ai.failed", study.id, t, error="AI service timeout")
            return

        inference = None
        if spec.ai:
            inference = self.store.add_inference(
                AIInference(
                    id=new_id("ai"),
                    study_id=study.id,
                    source=AISource.MOCK,
                    request_id=new_id("req"),
                    model_name=f"{spec.study_type}-triage",
                    model_version="0.1.0",
                    recommendation=spec.ai.recommendation,
                    confidence=spec.ai.confidence,
                    ranked_options=_ranked(spec.ai.recommendation, spec.ai.confidence),
                    reasons=tuple(Reason(c, label, w) for c, label, w in spec.ai.reasons),
                    latency_ms=spec.ai.latency_ms,
                    created_at=t,
                )
            )
            self.audit(
                doctor,
                "ai.analyzed",
                study.id,
                t,
                inference_id=inference.id,
                recommendation=str(inference.recommendation),
                confidence=inference.confidence,
            )

        if not spec.decision:
            return
        t += timedelta(hours=4)
        decision = self.store.add_decision(
            Decision(
                id=new_id("dc"),
                study_id=study.id,
                doctor_id=doctor.id,
                chosen_type=spec.decision.chosen_type,
                details=spec.decision.details,
                comment=spec.decision.comment,
                ai_inference_id=inference.id if inference else None,
                ai_recommendation=inference.recommendation if inference else None,
                ai_confidence=inference.confidence if inference else None,
                accepted_ai=compute_accepted_ai(
                    spec.decision.chosen_type, inference.recommendation if inference else None
                ),
                created_at=t,
            )
        )
        self.audit(
            doctor,
            "decision.created",
            study.id,
            t,
            decision_id=decision.id,
            chosen_type=str(decision.chosen_type),
            accepted_ai=decision.accepted_ai,
        )

        if not spec.notification:
            return
        n = spec.notification
        t += timedelta(minutes=30)
        notification = self.store.add_notification(
            Notification(
                id=new_id("nt"),
                decision_id=decision.id,
                study_id=study.id,
                patient_id=patient.id,
                channel=n.channel,
                text=notification_text(decision.chosen_type, decision.details),
                status=NotificationStatus.SENT,
                sent_at=t,
            )
        )
        self.audit(
            doctor,
            "notification.sent",
            study.id,
            t,
            notification_id=notification.id,
            channel=str(n.channel),
        )

        patient_user = self.store.get_user(patient.user_id)
        if n.read:
            t += timedelta(hours=3)
            notification.status = NotificationStatus.READ
            notification.read_at = t
            self.audit(
                patient_user, "notification.read", study.id, t, notification_id=notification.id
            )
        if n.booked_with:
            doctor_key, days, hour = n.booked_with
            t += timedelta(hours=1)
            appointment = self.store.add_appointment(
                Appointment(
                    id=new_id("ap"),
                    patient_id=patient.id,
                    doctor_id=self.users[doctor_key].id,
                    scheduled_for=_slot(self.now, self.tz, days, hour),
                    status=AppointmentStatus.SCHEDULED,
                    created_at=t,
                    notification_id=notification.id,
                )
            )
            notification.patient_action = PatientActionType.BOOKED
            notification.action_at = t
            notification.appointment_id = appointment.id
            self.audit(
                patient_user,
                "patient.booked",
                study.id,
                t,
                appointment_id=appointment.id,
                doctor_id=appointment.doctor_id,
            )


def seed_demo(store: Store, *, now: datetime | None = None, tz: str = "Europe/Moscow") -> None:
    now = now or datetime.now(UTC)
    # rounds=4: демо-пароль, а быстрый старт важнее стойкости хеша (bcrypt по умолчанию ~0.25 с)
    password_hash = hash_password(DEMO_PASSWORD, rounds=4)
    _Seeder(store, now, ZoneInfo(tz), password_hash).run()
