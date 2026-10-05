"""Протокол = описание находок «Поле- значение»; заключение отбрасывается; новое исследование."""

from app.domain.sr import parse_sr, report_text

API = "/api/v1"

# Как на thirdopinion.ai/chest_ct
CUSTOMER_SR = """Описание
Очаги и образования легких- не обнаружены
Грудная аорта- наибольшее значение диаметра восходящей части грудной аорты: 40 мм.
Обнаружена дилатация восходящей части грудной аорты
Коронарный кальций- кальциевый индекс (Agatston): 164; CAC DRS A2.
Качество исследования (PGMI): G
Заключение: Дилатация восходящей аорты.
BI-RADS 4"""


def test_parse_customer_format():
    fields = parse_sr(CUSTOMER_SR)
    assert [f.name for f in fields] == [
        "Очаги и образования легких",
        "Грудная аорта",
        "Коронарный кальций",
        "Качество исследования (PGMI)",
    ]
    # строка без разделителя — продолжение предыдущего значения; «:» внутри значения не режем
    assert fields[1].value.endswith("40 мм. Обнаружена дилатация восходящей части грудной аорты")
    assert fields[2].value == "кальциевый индекс (Agatston): 164; CAC DRS A2."
    # Заключение и всё после него в систему не берём
    assert all(f.value != "Дилатация восходящей аорты." for f in fields)
    # В AI — как report_text(t) у AI-команды, только описание
    text = report_text(fields)
    assert text.startswith("Описание: Очаги и образования легких: не обнаружены.")
    assert "Заключение" not in text and "BI-RADS" not in text


def test_create_study_from_sr(client, petrov, chief):
    patients = client.get(f"{API}/studies/patients", headers=petrov).json()
    pid = patients[0]["id"]
    body = {
        "patient_id": pid,
        "study_type": "ct",
        "body_region": "chest",
        "description": CUSTOMER_SR,
    }
    r = client.post(f"{API}/studies", headers=petrov, json=body)
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["status"] == "new" and card["can_act"]
    assert len(card["sr_fields"]) == 4 and "conclusion" not in card
    assert card["doctor"]["full_name"].startswith("Петров")  # врач создаёт себе

    # Тип без шаблона БФТ — нельзя; пустой протокол — нельзя
    bad = {**body, "study_type": "ultrasound", "body_region": "kidneys"}
    assert client.post(f"{API}/studies", headers=petrov, json=bad).status_code == 422
    empty = {**body, "description": "  "}
    assert client.post(f"{API}/studies", headers=petrov, json=empty).status_code == 422
    # Главврач обязан указать лечащего врача
    assert client.post(f"{API}/studies", headers=chief, json=body).status_code == 422
    r = client.post(
        f"{API}/studies",
        headers=chief,
        json={**body, "treating_doctor_id": card["doctor"]["id"]},
    )
    assert r.status_code == 200


def test_patient_cannot_create_or_list(client, kuznetsova):
    assert client.get(f"{API}/studies/patients", headers=kuznetsova).status_code == 403
