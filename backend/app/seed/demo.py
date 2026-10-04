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
    AppointmentStatus,
    NotificationStatus,
    PatientActionType,
    RecommendationType,
    Role,
    Sex,
    SocialNetwork,
    StudyStatus,
    StudyType,
)
from app.domain.models import (
    Appointment,
    AuditEvent,
    Decision,
    Delivery,
    Notification,
    Patient,
    Social,
    Study,
    User,
)
from app.domain.rules import (
    MAX_REMINDERS,
    REMINDER_INTERVAL,
    all_covered,
    contact_channels,
    needs_booking,
    needs_reminder,
)
from app.domain.sr import parse_sr
from app.services.notifications import delivery_targets, patient_texts, reminder_for
from app.store import Store

DEMO_PASSWORD = "demo"

R = RecommendationType
S = StudyStatus

# --- Персонал: (ключ, ФИО, email, роль, специальность) ---

STAFF = [
    ("chief", "Смирнова Ольга Николаевна", "chief@clinic.demo", Role.CHIEF, None),
    ("manager", "Лебедев Константин Ильич", "manager@clinic.demo", Role.MANAGER, None),
    ("petrov", "Петров Иван Сергеевич", "petrov@clinic.demo", Role.DOCTOR, "therapist"),
    ("sidorova", "Сидорова Анна Викторовна", "sidorova@clinic.demo", Role.DOCTOR, "pulmonologist"),
    ("kim", "Ким Алексей Дмитриевич", "kim@clinic.demo", Role.DOCTOR, "neurologist"),
    # Консультанты — к ним записываются пациенты
    ("orlov", "Орлов Дмитрий Андреевич", "orlov@clinic.demo", Role.DOCTOR, "orthopedist"),
    ("belova", "Белова Марина Юрьевна", "belova@clinic.demo", Role.DOCTOR, "oncologist"),
    ("gusev", "Гусев Павел Олегович", "gusev@clinic.demo", Role.DOCTOR, "gastroenterologist"),
    ("zakharov", "Захаров Игорь Валентинович", "zakharov@clinic.demo", Role.DOCTOR, "neurosurgeon"),
    # Для направлений из справочника AI-команды (кардиомегалия, аорта, надпочечник, онкология)
    ("egorova", "Егорова Светлана Павловна", "egorova@clinic.demo", Role.DOCTOR, "cardiologist"),
    ("titov", "Титов Роман Евгеньевич", "titov@clinic.demo", Role.DOCTOR, "endocrinologist"),
    ("frolov", "Фролов Денис Аркадьевич", "frolov@clinic.demo", Role.DOCTOR, "vascular_surgeon"),
    ("zaitseva", "Зайцева Ирина Олеговна", "zaitseva@clinic.demo", Role.DOCTOR, "radiotherapist"),
]

# --- Пациенты: (ключ, ФИО, email, дата рождения, пол, телефон) ---

# Соцсети указали не все пациенты — у остальных уведомление уйдёт в SMS и email
SOCIAL: dict[str, tuple[Social, ...]] = {
    "kuznetsova": (
        Social(SocialNetwork.TELEGRAM, "@kuznetsova_e"),
        Social(SocialNetwork.VK, "vk.com/kuznetsova_e"),
    ),
    "sokolov": (
        Social(SocialNetwork.TELEGRAM, "@m_sokolov"),
        Social(SocialNetwork.WHATSAPP, "+7 900 100-00-05"),
    ),
    "morozova": (Social(SocialNetwork.VK, "vk.com/n.morozova"),),
    "fedorova": (Social(SocialNetwork.TELEGRAM, "@irina_fed"),),
}

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
class DecisionSpec:
    chosen_types: tuple[RecommendationType, ...]
    details: dict[str, Any]
    comment: str | None = None


@dataclass
class NotificationSpec:
    read: bool = False
    # Записи по направлениям: (ключ направления, ключ врача или None для исследования,
    # через сколько дней, час)
    bookings: tuple[tuple[str, str | None, int, int], ...] = ()


@dataclass
class StudySpec:
    patient: str
    doctor: str
    study_type: StudyType
    body_region: str
    status: StudyStatus
    days_ago: int
    sr: str  # раздел «Описание» DICOM SR: строки «Поле- значение»
    decision: DecisionSpec | None = None
    notification: NotificationSpec | None = None
    conclusion: str | None = None  # заключение рентгенолога (может отсутствовать)
    extra: dict[str, Any] = field(default_factory=dict)


STUDIES: list[StudySpec] = [
    # Протоколы — раздел «Описание» DICOM SR по шаблонам БФТ («Поле- значение», как на
    # thirdopinion.ai). Только типы с шаблоном/справочником AI-команды: КТ ОГК, РГ ОГК, ММГ, КТ ГМ.
    # ---------- КТ органов грудной клетки ----------
    StudySpec(
        patient="ivanov",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NOTIFIED,
        days_ago=6,
        # tests/tests.md AI-команды, ct_chest_101
        sr="""Легочная ткань- очаг
Правое легкое- в S6 солидный очаг 9 мм с четкими контурами
Левое легкое- без очаговых и инфильтративных изменений
Трахея и бронхи- не выявлено признаков патологии
Плевральные полости- не выявлено признаков патологии
Средостение- не выявлено признаков патологии
Сердце и крупные сосуды- кальциноз коронарных артерий, Agatston 412, CAC-DRS 3
Костные структуры- не выявлено признаков патологии
Надпочечники- структурные изменения тела левого надпочечника, образование 18 мм, плотность 8 HU
Щитовидная железа- образование правой доли 14 мм""",
        conclusion=(
            "Солидный очаг S6 правого легкого 9 мм. Выраженный кальциноз коронарных артерий "
            "(CAC-DRS 3). Образование левого надпочечника 18 мм. Образование правой доли "
            "щитовидной железы."
        ),
        decision=DecisionSpec(
            (R.SPECIALIST_CONSULT, R.ADDITIONAL_RESEARCH),
            {"specialists": ["pulmonologist"], "research_types": ["ct"]},
            "Контрольная КТ через 3 месяца и консультация пульмонолога.",
        ),
        # Записался к пульмонологу, на КТ — ещё нет: кейс открыт (1 из 2)
        notification=NotificationSpec(
            read=True, bookings=(("specialist:pulmonologist", "sidorova", 2, 11),)
        ),
    ),
    StudySpec(
        patient="kuznetsova",
        doctor="petrov",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NOTIFIED,
        days_ago=5,
        sr="""Легочная ткань- участки консолидации
Левое легкое- в нижней доле (S9–S10) консолидация с воздушной бронхограммой 54×38 мм, по периферии зона «матового стекла»
Правое легкое- без очаговых и инфильтративных изменений
Плевральные полости- гидроторакс слева, толщина слоя до 8 мм
Средостение- внутригрудные лимфоузлы до 11 мм
Костные структуры- не выявлено признаков патологии""",
        conclusion="КТ-признаки левосторонней нижнедолевой пневмонии, малый левосторонний гидроторакс.",
        decision=DecisionSpec(
            (R.REPEAT_APPOINTMENT, R.SPECIALIST_CONSULT),
            {"specialists": ["pulmonologist"]},
            "Распространённая пневмония с выпотом — нужен пульмонолог и контрольный приём.",
        ),
        notification=NotificationSpec(),
    ),
    StudySpec(
        patient="popov",
        doctor="petrov",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=2,
        # tests/tests.md AI-команды, ct_chest_102
        sr="""Легочная ткань- эмфизема верхних долей обоих легких, общий объем 18%
Трахея и бронхи- бронхоэктазы в нижней доле правого легкого
Плевральные полости- не выявлено признаков патологии
Средостение- не выявлено признаков патологии
Сердце и крупные сосуды- аневризма/дилатация грудной аорты: восходящая аорта 46 мм, нисходящая 31 мм
Костные структуры- компрессионный перелом тела позвонка Th12, снижение высоты 32% (Genant 2)""",
        conclusion=(
            "Эмфизема легких. Бронхоэктазы нижней доли правого легкого. Дилатация восходящей "
            "аорты до 46 мм. Компрессионный перелом Th12 (Genant 2)."
        ),
    ),
    StudySpec(
        patient="vasilyeva",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=1,
        sr="""Легочная ткань- участки «матового стекла» в обоих легких полностью регрессировали
Правое легкое- остаточные тяжистые уплотнения в S10
Левое легкое- без очаговых и инфильтративных изменений
Плевральные полости- свободны
Средостение- не выявлено признаков патологии""",
        conclusion="Положительная динамика, полный регресс воспалительных изменений.",
    ),
    StudySpec(
        patient="volkov",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=0,
        # tests/tests.md AI-команды, ct_chest_103
        sr="""Легочная ткань- очаг(и)
Правое легкое- в S3 образование 27 мм с неровными контурами, множественные очаги до 6 мм в обоих легких
Трахея и бронхи- сужение просвета верхнедолевого бронха справа
Плевральные полости- гидроторакс справа, объем 250 мл
Средостение- лимфоаденопатия ВГЛУ, наибольший лимфоузел 19 мм
Костные структуры- не выявлено признаков патологии""",
        conclusion=(
            "Образование верхней доли правого легкого 27 мм с сужением верхнедолевого бронха. "
            "Множественные очаги обоих легких. Лимфоаденопатия ВГЛУ. Правосторонний гидроторакс."
        ),
    ),
    StudySpec(
        patient="ivanov",
        doctor="petrov",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=2,
        # tests/tests.md AI-команды, ct_chest_104: описания нет — только заключение
        sr="",
        conclusion=(
            "Очаговых и инфильтративных изменений в легких не выявлено. В зоне сканирования — "
            "образование тела левого надпочечника 16 мм, однородное, нативная плотность 4 HU. "
            "Других патологических изменений не выявлено."
        ),
    ),
    StudySpec(
        patient="novikov",
        doctor="sidorova",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=0,
        # Пример со страницы заказчика thirdopinion.ai/chest_ct (tests/site_tests.md)
        sr="""Очаги и образования легких- не обнаружены
Снижение воздушности легких- не обнаружено
Плевральный выпот- не обнаружен
Грудная аорта- наибольшее значение диаметра восходящей части грудной аорты: 40 мм. Обнаружена дилатация восходящей части грудной аорты; наибольшее значение диаметра нисходящей части грудной аорты: 33 мм
Легочный ствол- наибольший диаметр легочного ствола: 34 мм
Коронарный кальций- кальциевый индекс (Agatston): 164; CAC DRS A2
Паракардиальный жир- объем паракардиального жира: 387 мл, средняя плотность -96 HU
Компрессионный перелом позвоночника- деформация тел позвонков более 25 % отсутствует""",
    ),
    # ---------- Рентгенография / флюорография ОГК ----------
    StudySpec(
        patient="sokolov",
        doctor="petrov",
        study_type=StudyType.XRAY,
        body_region="chest",
        status=S.NEW,
        days_ago=1,
        sr="""Прозрачность легочных полей- сохранена
Очаговые изменения- не выявлены
Инфильтративные изменения- не выявлены
Легочный рисунок- без особенностей
Корни легких- структурны
Синусы- свободны
Диафрагма- контуры четкие
Тень сердца- не расширена""",
        conclusion="Патологических изменений органов грудной клетки не выявлено.",
    ),
    StudySpec(
        patient="morozova",
        doctor="petrov",
        study_type=StudyType.XRAY,
        body_region="chest",
        status=S.COMPLETED,
        days_ago=9,
        sr="""Прозрачность легочных полей- сохранена
Очаговые изменения- не выявлены
Инфильтративные изменения- не выявлены
Тень сердца- не расширена
Костные структуры- несросшийся перелом заднего отрезка VII ребра справа со смещением отломков""",
        conclusion="Несросшийся перелом VII ребра справа со смещением.",
        decision=DecisionSpec(
            (R.SPECIALIST_CONSULT,),
            {"specialists": ["orthopedist"]},
            "Консультация травматолога-ортопеда для решения о тактике лечения.",
        ),
        notification=NotificationSpec(
            read=True, bookings=(("specialist:orthopedist", "orlov", 3, 10),)
        ),
    ),
    StudySpec(
        patient="novikov",
        doctor="sidorova",
        study_type=StudyType.XRAY,
        body_region="chest",
        status=S.NOTIFIED,
        days_ago=3,
        # tests/tests.md AI-команды, xray_101
        sr="""Прозрачность легочных полей- снижена за счет инфильтрации/консолидации и признаков плеврального выпота
Инфильтративные изменения- инфильтрация в нижней доле правого легкого
Гидроторакс- плевральный выпот справа, синус справа затемнен
Синусы- синус слева свободный
Средостение- не изменено
Тень сердца- расширена, КТИ 0,56
Костные структуры- травматические изменения ребер не выявлены""",
        conclusion=(
            "Правосторонняя нижнедолевая инфильтрация. Правосторонний гидроторакс. Кардиомегалия."
        ),
        decision=DecisionSpec(
            (R.REPEAT_APPOINTMENT,),
            {},
            "Клинически лёгкое течение. Контроль после курса антибиотиков, КТ сейчас не нужна.",
        ),
    ),
    StudySpec(
        patient="fedorova",
        doctor="petrov",
        study_type=StudyType.XRAY,
        body_region="chest",
        status=S.NEW,
        days_ago=1,
        # Пример со страницы заказчика thirdopinion.ai/cxr (tests/site_tests.md)
        sr="""Легкие- очаговых и инфильтративных изменений не обнаружено
Костные структуры- обнаружен консолидированный перелом ребра
Сердце- тень сердца расширена, КТИ = 0,6""",
        conclusion="Очаговых и инфильтративных изменений не обнаружено. Кардиомегалия.",
    ),
    # ---------- Маммография ----------
    StudySpec(
        patient="lebedeva",
        doctor="petrov",
        study_type=StudyType.MAMMOGRAPHY,
        body_region="breast",
        status=S.NEW,
        days_ago=0,
        # tests/tests.md AI-команды, mmg_101
        sr="""Качество исследования (PGMI)- G
Правая молочная железа- плотность ACR C; кожа не изменена; кальцинаты подозрительные выявлены, верхне-наружный квадрант, сгруппированные (кластер); образования не выявлены; нарушение архитектоники не выявлено; аксиллярные лимфоузлы определяются, не изменены
Левая молочная железа- плотность ACR C; кожа не изменена; кальцинаты доброкачественные выявлены; образования не выявлены; нарушение архитектоники не выявлено; аксиллярные лимфоузлы определяются, не изменены""",
        conclusion="Правая молочная железа: BI-RADS 4. Левая молочная железа: BI-RADS 2.",
    ),
    StudySpec(
        patient="vasilyeva",
        doctor="petrov",
        study_type=StudyType.MAMMOGRAPHY,
        body_region="breast",
        status=S.NEW,
        days_ago=1,
        # Пример со страницы заказчика thirdopinion.ai/mmg (tests/site_tests.md)
        sr="""Качество исследования (PGMI)- G
Правая молочная железа- плотность ACR A; кожа не изменена; кальцинаты доброкачественные выявлены; кальцинаты подозрительные выявлены — 25 x 21 мм и 14 x 10 мм, в структуре образования; образование 36 x 26 мм, верхне-внутренний квадрант; нарушение архитектоники не выявлено; аксиллярные лимфоузлы определяются, не изменены; втяжение соска, асимметрия плотности, отёк ткани не выявлены""",
        conclusion="Правая молочная железа: BI-RADS 2.",
    ),
    # ---------- КТ головного мозга ----------
    StudySpec(
        patient="fedorova",
        doctor="kim",
        study_type=StudyType.CT,
        body_region="head",
        status=S.NEW,
        days_ago=2,
        # Пример со страницы заказчика thirdopinion.ai/head_ct (tests/site_tests.md)
        sr="""Смещение срединных структур- поперечное смещение 3 мм
Внутричерепные кровоизлияния- признаки не обнаружены
Ишемический инсульт- признаки не обнаружены
Кистозно-глиозная трансформация- признаки обнаружены, срезы 52–95
Вентрикуло-краниальные коэффициенты- ВКК1 26 %, ВКК2 16 %, ВКК3 7 %, ширина III желудочка 9 мм
Миндалины мозжечка- выше края большого затылочного отверстия""",
        conclusion=(
            "КТ-картина кистозно-глиозной трансформации, смещение срединных структур 3 мм. "
            "Геморрагических и ишемических изменений не выявлено."
        ),
    ),
    StudySpec(
        patient="popov",
        doctor="kim",
        study_type=StudyType.CT,
        body_region="head",
        status=S.NOTIFIED,
        days_ago=4,
        sr="""Смещение срединных структур- не выявлено
Внутричерепные кровоизлияния- признаки не обнаружены
Ишемический инсульт- признаки не обнаружены
Белое вещество- перивентрикулярный лейкоареоз, единичные лакунарные очаги в базальных ядрах до 4 мм
Желудочковая система- расширена умеренно, ВКК1 28 %""",
        conclusion="КТ-признаки хронической ишемии головного мозга, умеренная заместительная гидроцефалия.",
        decision=DecisionSpec(
            (R.REPEAT_APPOINTMENT,),
            {},
            "Контроль факторов риска, повторный осмотр через полгода.",
        ),
    ),
    StudySpec(
        patient="sokolov",
        doctor="kim",
        study_type=StudyType.CT,
        body_region="head",
        status=S.NOTIFIED,
        days_ago=9,  # уведомлён больше недели назад — уже было напоминание
        sr="""Смещение срединных структур- смещение влево до 4 мм
Внутричерепные кровоизлияния- признаки не обнаружены
Объемные образования- экстрааксиальное образование правой лобной области 32 мм, широким основанием прилежит к твердой мозговой оболочке, перифокальный отек
Ишемический инсульт- признаки не обнаружены""",
        conclusion="КТ-картина объемного образования правой лобной области (вероятно, менингиома).",
        decision=DecisionSpec(
            (R.SPECIALIST_CONSULT,),
            {"specialists": ["neurosurgeon"]},
            "Консультация нейрохирурга: решить вопрос об оперативном лечении.",
        ),
        notification=NotificationSpec(read=True),
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


def _slot(now: datetime, tz: ZoneInfo, days_ahead: int, hour: int, minute: int = 0) -> datetime:
    """Рабочий слот через N дней (выходные пропускаем вперёд до понедельника)."""
    day = now.astimezone(tz).date() + timedelta(days=days_ahead)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(hour, minute), tzinfo=tz).astimezone(UTC)


class _Seeder:
    def __init__(
        self,
        store: Store,
        now: datetime,
        tz: ZoneInfo,
        password_hash: str,
        contact_phone: str = "",
        contact_email: str = "",
    ) -> None:
        self.store = store
        self.now = now
        self.tz = tz
        self.pw = password_hash
        # Демо на сцене: у всех пациентов один телефон и почта — уведомления придут одному человеку
        self.contact_phone = contact_phone
        self.contact_email = contact_email or None
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
                    phone=self.contact_phone or phone,
                    contact_email=self.contact_email,
                    socials=SOCIAL.get(key, ()),
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
                sr_fields=tuple(parse_sr(spec.sr)[0]),
                conclusion=spec.conclusion,
            )
        )
        self.audit(doctor, "study.created", study.id, created_at)

        # Ответов AI в seed нет — их даёт только реальный сервис (автоанализ после старта).
        # Решения в истории приняты врачами без AI.
        if not spec.decision:
            return
        t = created_at + timedelta(hours=4)
        decision = self.store.add_decision(
            Decision(
                id=new_id("dc"),
                study_id=study.id,
                doctor_id=doctor.id,
                chosen_types=spec.decision.chosen_types,
                details=spec.decision.details,
                comment=spec.decision.comment,
                ai_inference_id=None,
                ai_recommendation=None,
                ai_confidence=None,
                accepted_ai=None,
                created_at=t,
            )
        )
        self.audit(
            doctor,
            "decision.created",
            study.id,
            t,
            decision_id=decision.id,
            chosen_types=[str(c) for c in decision.chosen_types],
            accepted_ai=None,
        )

        # Уведомление уходит сразу после решения (во все доступные каналы)
        n = spec.notification or NotificationSpec()
        t += timedelta(seconds=1)
        nid = new_id("nt")
        text, short = patient_texts(self.store, decision, study, nid)
        notification = self.store.add_notification(
            Notification(
                id=nid,
                decision_id=decision.id,
                study_id=study.id,
                patient_id=patient.id,
                channels=contact_channels(patient, self.store.get_user(patient.user_id)),
                text=text,
                short_text=short.message,
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
            channels=[str(c) for c in notification.channels],
        )

        patient_user = self.store.get_user(patient.user_id)
        if n.read:
            t += timedelta(hours=3)
            notification.status = NotificationStatus.READ
            notification.read_at = t
            self.audit(
                patient_user, "notification.read", study.id, t, notification_id=notification.id
            )
        for requirement, doctor_key, days, hour in n.bookings:
            t += timedelta(hours=1)
            appointment = self.store.add_appointment(
                Appointment(
                    id=new_id("ap"),
                    patient_id=patient.id,
                    doctor_id=self.users[doctor_key].id if doctor_key else None,
                    research_type=None if doctor_key else requirement.split(":", 1)[1],
                    scheduled_for=_slot(self.now, self.tz, days, hour),
                    status=AppointmentStatus.SCHEDULED,
                    created_at=t,
                    notification_id=notification.id,
                    requirement=requirement,
                )
            )
            if notification.patient_action is None:
                notification.action_at = t
            notification.patient_action = PatientActionType.BOOKED
            notification.appointment_id = appointment.id
            self.audit(
                patient_user,
                "patient.booked",
                study.id,
                t,
                appointment_id=appointment.id,
                requirement=requirement,
            )
        # Кейс закрыт, только если записи есть по всем направлениям
        appointments = self.store.list_appointments(notification_id=notification.id)
        assert (study.status is S.COMPLETED) == all_covered(decision, appointments), spec.patient

        # История отправок: первое уведомление и напоминания раз в неделю, пока пациент
        # не записался (как делает services/reminders.py)
        targets = delivery_targets(self.store, patient)
        sent_at = notification.sent_at
        notification.deliveries = [
            Delivery(sent_at, c, target, 0, short.for_channel(c)) for c, target in targets
        ]
        if not needs_booking(decision):
            return
        due = sent_at + REMINDER_INTERVAL
        while (
            needs_reminder(notification, decision, appointments)
            and notification.reminders_sent < MAX_REMINDERS
            and due <= self.now
        ):
            notification.reminders_sent += 1
            notification.deliveries += [
                Delivery(
                    due,
                    c,
                    target,
                    notification.reminders_sent,
                    reminder_for(self.store, notification).for_channel(c),
                )
                for c, target in targets
            ]
            self.audit(
                None,
                "notification.reminder",
                study.id,
                due,
                notification_id=notification.id,
                attempt=notification.reminders_sent,
                of=MAX_REMINDERS,
            )
            due += REMINDER_INTERVAL
        if needs_reminder(notification, decision, appointments):
            notification.next_reminder_at = (
                due if notification.reminders_sent < MAX_REMINDERS else None
            )


def seed_demo(
    store: Store,
    *,
    now: datetime | None = None,
    tz: str = "Europe/Moscow",
    contact_phone: str = "",
    contact_email: str = "",
) -> None:
    """contact_phone / contact_email — общие контакты всех пациентов (DEMO_CONTACT_* в .env).

    История доставок seed — всегда имитация: при старте ничего не отправляется."""
    now = now or datetime.now(UTC)
    # rounds=4: демо-пароль, а быстрый старт важнее стойкости хеша (bcrypt по умолчанию ~0.25 с)
    password_hash = hash_password(DEMO_PASSWORD, rounds=4)
    _Seeder(store, now, ZoneInfo(tz), password_hash, contact_phone, contact_email).run()
