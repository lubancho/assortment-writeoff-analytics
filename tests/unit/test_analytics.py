"""Модульные тесты аналитики: ABC, XYZ, метрики запасов и списаний, рекомендации (ТЗ §29)."""

from datetime import date, timedelta
from decimal import Decimal as Dec

import numpy as np
import pandas as pd
import pytest

from asa import abc, metrics, recommendations, xyz

# --- ABC ---------------------------------------------------------------------------------------------


def values(pairs):
    return pd.DataFrame(pairs, columns=["product_id", "value"])


def test_abc_boundary_item_stays_in_higher_class():
    # Доли: 50, 25, 10, 8, 4, 3 (%). Накопленная до товара: 0, 50, 75, 85, 93, 97.
    df = abc.classify(values([(1, 50), (2, 25), (3, 10), (4, 8), (5, 4), (6, 3)]))
    assert df.set_index("product_id")["abc_class"].to_dict() == {
        1: "A",
        2: "A",
        3: "A",
        4: "B",
        5: "B",
        6: "C",
    }
    # Товар 3 переводит накопленную долю за 80% (75 → 85), но начинается до границы — остаётся в A.
    row = df.set_index("product_id").loc[3]
    assert row["cum_before"] == Dec("0.75") and row["cum_share"] == Dec("0.85")


def test_abc_ties_sorted_by_product_id():
    df = abc.classify(values([(5, 10), (2, 10), (9, 10)]))
    assert df["product_id"].tolist() == [2, 5, 9]


def test_abc_zero_and_negative_contribution_go_to_c_and_are_not_in_denominator():
    df = abc.classify(values([(1, 90), (2, 10), (3, 0), (4, -20)])).set_index("product_id")
    assert df.loc[1, "share"] == Dec("0.9") and df.loc[2, "share"] == Dec("0.1")
    assert df.loc[3, "abc_class"] == "C" and df.loc[3, "note"] == "нет продаж"
    assert df.loc[4, "abc_class"] == "C" and df.loc[4, "note"] == "отрицательный вклад"


def test_abc_custom_thresholds_and_validation():
    df = abc.classify(
        values([(1, 60), (2, 30), (3, 10)]), abc.AbcThresholds(Dec("0.5"), Dec("0.8"))
    )
    assert df["abc_class"].tolist() == ["A", "B", "C"]
    with pytest.raises(ValueError):
        abc.classify(values([(1, 1)]), abc.AbcThresholds(Dec("0.9"), Dec("0.8")))


def test_abc_revenue_and_profit_classes_can_differ():
    rev = abc.classify(values([(1, 100), (2, 90), (3, 10)])).set_index("product_id")["abc_class"]
    # Прибыль: 2 / 60 / 8 → у товара 1 накопленная доля до него 97% — класс C.
    gp = abc.classify(values([(1, 2), (2, 60), (3, 8)])).set_index("product_id")["abc_class"]
    assert rev[1] == "A" and gp[1] == "C"


def test_abc_summary_sums_to_total():
    df = abc.classify(values([(1, 50), (2, 25), (3, 10), (4, 8), (5, 4), (6, 3)]))
    s = abc.summary(df)
    assert s["products"].sum() == 6 and sum(s["share"]) == Dec(1)


# --- XYZ ---------------------------------------------------------------------------------------------


def weekly(pid, qtys, availability=None, start=date(2026, 8, 3)):
    availability = availability or [1.0] * len(qtys)
    return pd.DataFrame(
        {
            "product_id": pid,
            "week_start": [start + timedelta(weeks=i) for i in range(len(qtys))],
            "net_qty": qtys,
            "availability": availability,
        }
    )


def test_cv_formula_and_classes():
    stable = weekly(1, [100, 102, 98, 101, 99, 100])
    volatile = weekly(2, [10, 50, 5, 60, 20, 80])
    medium = weekly(3, [100, 130, 80, 120, 85, 110])
    res = xyz.classify(pd.concat([stable, volatile, medium])).set_index("product_id")
    assert (
        res.loc[1, "xyz_class"] == "X"
        and res.loc[2, "xyz_class"] == "Z"
        and res.loc[3, "xyz_class"] == "Y"
    )
    expected = np.std([100, 102, 98, 101, 99, 100]) / 100
    assert res.loc[1, "cv"] == pytest.approx(expected)


def test_weeks_with_low_availability_are_excluded():
    # Неделя 3: товар был доступен в 40% дней — провал продаж не считается падением спроса.
    df = weekly(1, [100, 101, 5, 99, 100, 102, 98], [1, 1, 0.4, 1, 1, 1, 1])
    res = xyz.classify(df).iloc[0]
    assert res["weeks_excluded"] == 1 and res["xyz_class"] == "X"


def test_too_few_observations_and_no_sales_and_short_history():
    few = weekly(1, [10, 12, 11])
    none = weekly(2, [0] * 8)
    young = weekly(3, [10] * 8)
    res = xyz.classify(
        pd.concat([few, none, young]),
        first_sale={3: date(2026, 9, 20)},
        period_start=date(2026, 8, 3),
    ).set_index("product_id")
    assert res.loc[1, "note"] == "недостаточно наблюдений" and res.loc[1, "xyz_class"] is None
    assert res.loc[2, "note"] == "нет продаж" and res.loc[2, "xyz_class"] is None
    assert res.loc[3, "note"] == "недостаточная история"


def test_detrend_reduces_cv_for_seasonal_trend():
    trend = [50, 60, 70, 80, 90, 100, 110, 120]
    plain = xyz.coefficient_of_variation(np.array(trend))
    detrended = xyz.coefficient_of_variation(np.array(trend), detrend=True)
    assert plain > 0.25 and detrended < 0.01


def test_full_weeks_inside_period():
    assert xyz.full_weeks(date(2026, 8, 5), date(2026, 8, 30)) == (
        date(2026, 8, 10),
        date(2026, 8, 30),
    )
    assert xyz.full_weeks(date(2026, 8, 5), date(2026, 8, 9)) is None


def test_xyz_settings_validation():
    with pytest.raises(ValueError):
        xyz.classify(weekly(1, [1] * 8), xyz.XyzSettings(x_max=0.3, y_max=0.2))


# --- Метрики запасов и списаний -------------------------------------------------------------------


def test_write_off_share_and_zero_denominator():
    assert metrics.write_off_share(Dec(20), Dec(80)) == Dec("0.2")
    assert metrics.write_off_share(Dec(0), Dec(0)) is None


def test_turnover_and_days_of_supply():
    # Себестоимость продаж 28 000 ₽ за 28 дней, средний доступный запас 2 000 ₽ в день → 14 раз.
    assert metrics.turnover(Dec(28000), Dec(56000), 28) == Dec(14)
    # Остаток 3 000 ₽ при продажах 1 000 ₽ в день → 3 дня запаса.
    assert metrics.days_of_supply(Dec(3000), Dec(28000), 28) == Dec(3)


def test_no_stock_gives_none_not_zero():
    assert metrics.turnover(Dec(1000), Dec(0), 28) is None
    assert metrics.days_of_supply(Dec(0), Dec(0), 28) is None
    assert metrics.out_of_stock_share(0, 0) is None


def test_avg_check_requires_orders():
    m = metrics.from_sums(Dec(1000), Dec(1000), Dec(600), Dec(10), 0, orders=4)
    assert m.avg_check == Dec(250)
    assert metrics.from_sums(Dec(1000), Dec(1000), Dec(600), Dec(10), 0, orders=0).avg_check is None


def lines(rows):
    cols = [
        "sale_line_id",
        "order_id",
        "sale_date",
        "store_id",
        "product_id",
        "quantity",
        "unit_price",
        "discount_amount",
        "operation_type",
        "is_cancelled",
    ]
    return pd.DataFrame(rows, columns=cols)


def test_returns_cancellations_and_avg_check_python():
    d = date(2026, 10, 1)
    df = lines(
        [
            (1, 10, d, 1, 1, 2, 100.0, 0.0, "sale", False),
            (2, 10, d, 1, 1, 1, 100.0, 0.0, "return", False),
            (3, 11, d, 1, 1, 1, 300.0, 0.0, "sale", False),
            (4, 12, d, 1, 1, 5, 100.0, 0.0, "sale", True),
        ]
    )
    costs = pd.DataFrame(
        {"product_id": [1], "valid_from": [date(2026, 1, 1)], "unit_cost": [Dec(50)]}
    )
    m = metrics.python_sales_totals(df, costs)
    assert m.revenue == Dec("400.00") and m.net_qty == Dec(2)
    assert m.orders == 2 and m.avg_check == Dec(200)  # отменённый чек не считается


def test_write_off_cost_uses_cost_on_write_off_date():
    wo = pd.DataFrame(
        {
            "write_off_date": [date(2026, 9, 1), date(2026, 10, 2)],
            "product_id": [1, 1],
            "quantity": [2, 1],
        }
    )
    costs = pd.DataFrame(
        {
            "product_id": [1, 1],
            "valid_from": [date(2026, 1, 1), date(2026, 10, 1)],
            "unit_cost": [Dec(50), Dec(70)],
        }
    )
    assert metrics.python_write_off_cost(wo, costs) == Dec(170)


def test_contribution_with_negative_values():
    df = pd.DataFrame({"gp": [Dec(120), Dec(-20)]})
    shares = metrics.contribution(df, "gp").tolist()
    assert shares == [Dec("1.2"), Dec("-0.2")]


# --- Рекомендации ------------------------------------------------------------------------------------


def analysis_row(**over):
    base = dict(
        product_id=1,
        sku="RL-0001",
        name="Ролл",
        category_name="Роллы",
        is_active=True,
        revenue=Dec(100000),
        revenue_costed=Dec(100000),
        gross_profit=Dec(45000),
        gross_margin=Dec("0.45"),
        abc_revenue="B",
        revenue_share=Dec("0.01"),
        xyz_class="Y",
        cv=0.2,
        oos_share=Dec("0.01"),
        unavailable_days=4,
        sold_out_days=10,
        open_days=400,
        write_off_share=Dec("0.10"),
        write_off_cost=Dec(5000),
        has_prev_period=False,
        revenue_prev=None,
        gross_profit_prev=None,
    )
    base.update(over)
    return base


def frame(*rows):
    # Фоновые товары задают маржу сети (≈ 45%) и медиану списаний категории (10%).
    background = [analysis_row(product_id=100 + i, sku=f"X{i}", name=f"Фон {i}") for i in range(6)]
    return pd.DataFrame([*background, *rows])


def rules_for(df, pid):
    r = recommendations.build(df)
    return set(r[r["product_id"] == pid]["rule"])


def test_rule_r1_high_revenue_low_margin():
    df = frame(
        analysis_row(
            product_id=1, abc_revenue="A", gross_profit=Dec(30000), gross_margin=Dec("0.30")
        )
    )
    assert rules_for(df, 1) == {"R1"}


def test_rule_r2_stable_demand_frequent_absence():
    df = frame(
        analysis_row(product_id=1, xyz_class="X", oos_share=Dec("0.05"), unavailable_days=20)
    )
    assert rules_for(df, 1) == {"R2"}
    df = frame(analysis_row(product_id=1, xyz_class="Z", oos_share=Dec("0.05")))
    assert "R2" not in rules_for(df, 1)


def test_rule_r3_write_offs_compared_within_category():
    df = frame(analysis_row(product_id=1, write_off_share=Dec("0.50")))
    r = recommendations.build(df)
    row = r[r["product_id"] == 1].iloc[0]
    assert row["rule"] == "R3" and row["severity"] == "Высокая"
    df = frame(
        analysis_row(product_id=1, write_off_share=Dec("0.20"))
    )  # +10 п. п. к медиане — ниже порога
    assert "R3" not in rules_for(df, 1)


def test_rule_r4_low_contribution_unstable_demand_never_suggests_removal():
    df = frame(analysis_row(product_id=1, abc_revenue="C", xyz_class="Z"))
    r = recommendations.build(df)
    row = r[r["product_id"] == 1].iloc[0]
    assert row["rule"] == "R4"
    text = " ".join(r.astype(str).agg(" ".join, axis=1)).lower()
    assert "вывести товар" not in row["action"].lower()
    assert "не основание для вывода" in row["limitations"]
    assert "исключить из ассортимента" not in text


def test_rule_r5_profit_falls_while_revenue_grows():
    df = frame(
        analysis_row(
            product_id=1,
            has_prev_period=True,
            revenue_prev=Dec(90000),
            gross_profit_prev=Dec(50000),
        )
    )
    assert rules_for(df, 1) == {"R5"}
    df = frame(
        analysis_row(
            product_id=1,
            has_prev_period=False,
            revenue_prev=Dec(90000),
            gross_profit_prev=Dec(50000),
        )
    )
    assert rules_for(df, 1) == set()


def test_every_recommendation_has_all_required_fields():
    df = frame(
        analysis_row(
            product_id=1, abc_revenue="A", gross_margin=Dec("0.2"), write_off_share=Dec("0.6")
        )
    )
    r = recommendations.build(df)
    for col in ("problem", "basis", "value", "possible_cause", "action", "limitations"):
        assert r[col].map(lambda s: isinstance(s, str) and len(s) > 5).all(), col
    assert r["severity"].tolist() == sorted(r["severity"], key=recommendations.SEVERITY_ORDER.get)
