"""Проверки качества данных и экспорт (общие с проектом №1)."""

from datetime import date
from decimal import Decimal as Dec

import pandas as pd
from openpyxl import load_workbook

from asa import quality
from asa.export import to_csv_bytes, to_xlsx_bytes


def lines(rows):
    cols = [
        "sale_line_id",
        "order_id",
        "sold_at",
        "sale_date",
        "store_id",
        "product_id",
        "quantity",
        "unit_price",
        "discount_amount",
        "operation_type",
        "is_cancelled",
        "promo_id",
    ]
    return pd.DataFrame(rows, columns=cols)


def line(
    i, qty=1, price=100.0, disc=0.0, op="sale", cancelled=False, product=1, day=date(2026, 10, 1)
):
    return (
        i,
        i,
        pd.Timestamp(day, tz="Asia/Omsk"),
        day,
        1,
        product,
        qty,
        price,
        disc,
        op,
        cancelled,
        None,
    )


# --- Качество данных ---------------------------------------------------------------------------


# TC-11
def test_duplicates_are_removed_and_logged():
    df = lines([line(1), line(1), line(2)])
    res = quality.check_sale_lines(df, {1}, {1}, set())
    assert len(res.valid) == 2 and res.count("DUPLICATE") == 1


def test_fk_range_and_discount_checks():
    df = lines(
        [
            line(1, product=999),
            line(2, qty=0),
            line(3, price=-1.0),
            line(4, qty=1, price=100.0, disc=150.0),
            line(5, op="refund"),
            line(6),
        ]
    )
    res = quality.check_sale_lines(df, {1}, {1}, set())
    assert res.count("FK_VIOLATION") == 1
    assert res.count("OUT_OF_RANGE") == 3
    assert res.count("DISCOUNT_OUT_OF_RANGE") == 1
    assert res.valid["sale_line_id"].tolist() == [6]


def test_missing_values_are_rejected():
    df = lines([line(1)])
    df.loc[0, "unit_price"] = None
    res = quality.check_sale_lines(df, {1}, {1}, set())
    assert res.count("MISSING_VALUE") == 1 and res.valid.empty


def test_cost_and_price_checks():
    costs = pd.DataFrame(
        {
            "product_id": [1, 2, 3, 3],
            "valid_from": [date(2026, 1, 1)] * 4,
            "unit_cost": [10.0, 0.0, -5.0, 7.0],
            "source": "x",
            "calc_version": 1,
        }
    )
    res = quality.check_costs(costs, {1, 2, 3})
    # товар 3: первая строка — себестоимость −5, вторая — дубль по ключу «товар + дата»
    assert res.count("NON_POSITIVE_COST") == 2 and res.count("DUPLICATE") == 1
    assert res.valid["product_id"].tolist() == [1]
    prices = pd.DataFrame(
        {
            "store_id": [1, 1, 9],
            "product_id": [1, 2, 1],
            "valid_from": [date(2026, 1, 1)] * 3,
            "price": [100.0, 0.0, 100.0],
        }
    )
    res = quality.check_prices(prices, {1}, {1, 2})
    assert res.count("NON_POSITIVE_PRICE") == 1 and res.count("FK_VIOLATION") == 1


def test_missing_price_completeness_check():
    prices = pd.DataFrame(
        {
            "store_id": [1, 1, 2],
            "product_id": [1, 2, 1],
            "valid_from": [date(2026, 1, 1), date(2026, 12, 1), date(2026, 1, 1)],
        }
    )
    issues = quality.check_missing_prices(prices, [1, 2], [1, 2], date(2026, 10, 31))
    assert sorted((i["store_id"], i["product_id"]) for i in issues) == [(1, 2), (2, 2)]


# --- Экспорт ------------------------------------------------------------------------------------


def test_export_keeps_types(tmp_path):
    df = pd.DataFrame(
        {"Товар": ["Ролл"], "Цена": [Dec("249.00")], "Дата": [date(2026, 10, 31)], "Кол-во": [3]}
    )
    xlsx = tmp_path / "x.xlsx"
    xlsx.write_bytes(to_xlsx_bytes({"Данные": df}, {"Период": "тест"}))
    ws = load_workbook(xlsx)["Данные"]
    assert isinstance(ws["B2"].value, int | float) and ws["B2"].value == 249
    assert ws["B2"].number_format == "#,##0.00"
    assert ws["C2"].is_date
    assert isinstance(ws["D2"].value, int)
    assert "синтетические" in load_workbook(xlsx)["Описание"]["A1"].value
    csv = to_csv_bytes(df).decode("utf-8-sig")
    assert "249,0" in csv and csv.startswith("# Демонстрационные")
