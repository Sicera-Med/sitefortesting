"""Демо-набор (SPEC §9): персонал, пациенты, исследования и сценарии решений.

Все данные синтетические: ФИО, телефоны и почты вымышлены, совпадения случайны.
Протоколы — сырые поля DICOM SR «Поле- значение» по шаблонам БФТ (КТ ОГК, РГ/ФЛГ ОГК,
маммография, КТ ГМ), как на сайте заказчика thirdopinion.ai; часть — из тестовых протоколов
AI-команды. Ответов AI здесь нет: их даёт только реальная модель.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.domain.enums import (
    RecommendationType,
    Role,
    Sex,
    StudyStatus,
    StudyType,
)

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
    sr: str  # описание из протокола: строки «Поле- значение»
    decision: DecisionSpec | None = None
    notification: NotificationSpec | None = None
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
    ),
    StudySpec(
        patient="ivanov",
        doctor="petrov",
        study_type=StudyType.CT,
        body_region="chest",
        status=S.NEW,
        days_ago=2,
        # tests/tests.md AI-команды, ct_chest_104: находки из заключения — строками описания
        sr="""Очаги и образования легких- не обнаружены
Инфильтративные изменения- не выявлены
Надпочечники- в зоне сканирования образование тела левого надпочечника 16 мм, однородное, нативная плотность 4 HU""",
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
