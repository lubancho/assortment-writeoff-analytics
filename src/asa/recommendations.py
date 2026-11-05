"""Правила управленческих рекомендаций (ТЗ §25; документ 04, раздел 6).

Простыми словами: каждое правило — это вопрос к данным («у товара большая выручка, но низкая маржа?»).
Если ответ «да», формируется рекомендация с основанием, значением показателя, возможной причиной,
действием и ограничениями. Правила не утверждают причину — они говорят, ЧТО проверить.
Ни одно правило не рекомендует выводить товар из ассортимента только по классу ABC/XYZ.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from asa.metrics import D, safe_ratio

SEVERITY_ORDER = {"Высокая": 0, "Средняя": 1, "Низкая": 2}


@dataclass(frozen=True)
class RuleSettings:
    low_margin_gap_pp: Decimal = Decimal("0.05")  # R1: маржа ниже сетевой более чем на 5 п. п.
    oos_share: Decimal = Decimal(
        "0.03"
    )  # R2: товара не было в продаже в ≥ 3% рабочих точко-дней (цель — доступность 97%)
    write_off_share: Decimal = Decimal(
        "0.20"
    )  # R3: не меньше 20% себестоимости выпуска уходит в списание
    write_off_vs_category_pp: Decimal = Decimal(
        "0.15"
    )  # R3: и выше медианы своей категории на 15 п. п.
    write_off_high_pp: Decimal = Decimal(
        "0.30"
    )  # R3: высокая важность — выше медианы категории на 30 п. п.
    gp_drop_share: Decimal = Decimal("0.03")  # R5: прибыль упала более чем на 3% при росте выручки


def _pct(x) -> str:
    return "н/д" if x is None else f"{float(x) * 100:.1f}%".replace(".", ",")


def _pp(x) -> str:
    """Разница долей в процентных пунктах: 0,15 → «15 п. п.»."""
    return f"{float(x) * 100:g} п. п.".replace(".", ",")


def _rub(x) -> str:
    return f"{float(D(x)):,.0f} ₽".replace(",", " ")


def _rec(
    row,
    rule: str,
    severity: str,
    problem: str,
    basis: str,
    value: str,
    cause: str,
    action: str,
    limits: str,
) -> dict:
    return {
        "rule": rule,
        "severity": severity,
        "product_id": int(row.product_id),
        "sku": row.sku,
        "product_name": row.name,
        "category_name": row.category_name,
        "problem": problem,
        "basis": basis,
        "value": value,
        "possible_cause": cause,
        "action": action,
        "limitations": limits,
    }


def build(analysis: pd.DataFrame, settings: RuleSettings | None = None) -> pd.DataFrame:
    """analysis — результат asa.analysis.product_analysis."""
    settings = settings or RuleSettings()
    active = analysis[analysis["is_active"]]
    total_rev = sum((D(v) for v in active["revenue_costed"]), Decimal(0))
    total_gp = sum((D(v) for v in active["gross_profit"]), Decimal(0))
    network_margin = safe_ratio(total_gp, total_rev)
    # Норма списаний сравнивается внутри категории: у свежей продукции списания выше по природе.
    category_median = {
        cat: Decimal(
            str(pd.Series([float(v) for v in grp if v is not None and not pd.isna(v)]).median())
        )
        for cat, grp in active.groupby("category_name")["write_off_share"]
    }
    out: list[dict] = []
    for r in active.itertuples(index=False):
        margin = (
            r.gross_margin if r.gross_margin is not None and not pd.isna(r.gross_margin) else None
        )

        # R1. Высокая выручка и низкая маржа.
        if (
            r.abc_revenue == "A"
            and margin is not None
            and network_margin is not None
            and margin < network_margin - settings.low_margin_gap_pp
        ):
            out.append(
                _rec(
                    r,
                    "R1",
                    "Высокая",
                    "Высокая выручка при низкой марже",
                    f"Класс A по выручке; маржинальность ниже сетевой ({_pct(network_margin)}) "
                    f"более чем на {_pp(settings.low_margin_gap_pp)}",
                    f"Маржинальность {_pct(margin)}, выручка {_rub(r.revenue)}",
                    "Рост себестоимости без пересмотра цены, глубокие скидки или промо",
                    "Проверить себестоимость (техкарта, закупочные цены), действующую цену и участие в промо",
                    "Маржа — валовая: аренда и персонал не учтены. Низкая маржа может быть осознанной "
                    "(товар-приманка)",
                )
            )

        # R2. Стабильный спрос и частое отсутствие товара.
        if (
            r.xyz_class in ("X", "Y")
            and r.oos_share is not None
            and not pd.isna(r.oos_share)
            and r.oos_share >= settings.oos_share
        ):
            out.append(
                _rec(
                    r,
                    "R2",
                    "Высокая" if r.xyz_class == "X" else "Средняя",
                    "Стабильный спрос, но товара часто нет",
                    f"Класс {r.xyz_class} по XYZ; товара не было в продаже "
                    f"в {_pct(r.oos_share)} рабочих точко-дней (порог {_pct(settings.oos_share)})",
                    f"Нет в продаже: {int(r.unavailable_days)} из {int(r.open_days)} точко-дней; "
                    f"распродан к закрытию: {int(r.sold_out_days)}",
                    "Объём производства или поставки меньше спроса; сбои поставок",
                    "Проверить план производства и страховой запас для дней с высоким спросом",
                    "В дни отсутствия продажи равны нулю, но это не нулевой спрос: настоящий спрос в такие дни "
                    "неизвестен. Причина отсутствия (поставка, производство, решение точки) в данных не указана",
                )
            )

        # R3. Высокие списания (по сравнению с товарами своей категории).
        ws = r.write_off_share
        norm = category_median.get(r.category_name)
        if (
            ws is not None
            and not pd.isna(ws)
            and norm is not None
            and ws >= settings.write_off_share
            and ws >= norm + settings.write_off_vs_category_pp
        ):
            out.append(
                _rec(
                    r,
                    "R3",
                    "Высокая" if ws >= norm + settings.write_off_high_pp else "Средняя",
                    "Высокая доля списаний",
                    f"Доля списаний в себестоимости выпуска выше медианы категории «{r.category_name}» "
                    f"({_pct(norm)}) более чем на {_pp(settings.write_off_vs_category_pp)}",
                    f"Списано на {_rub(r.write_off_cost)} — {_pct(ws)} себестоимости выпуска",
                    "Производство с избыточным запасом, неточный прогноз спроса, малые объёмы продаж "
                    "при минимальной партии",
                    "Сверить объём производства с фактическими продажами по дням недели, уточнить прогноз",
                    "Связь с объёмом производства — гипотеза: причины списаний нужно проверить на месте. "
                    "Для свежей продукции часть списаний неизбежна",
                )
            )

        # R4. Низкий вклад и нестабильный спрос.
        if r.abc_revenue == "C" and r.xyz_class == "Z":
            out.append(
                _rec(
                    r,
                    "R4",
                    "Низкая",
                    "Низкий вклад и нестабильный спрос",
                    "Класс C по выручке и класс Z по XYZ",
                    f"Доля в выручке {_pct(r.revenue_share)}, коэффициент вариации {_pct(r.cv)}",
                    "Нишевый товар, неудачное расположение в меню, сезонный спрос",
                    "Провести дополнительную ассортиментную оценку: роль товара в чеке, отзывы, "
                    "сезонность, маржинальность",
                    "Класс ABC/XYZ — не основание для вывода товара из ассортимента",
                )
            )

        # R5. Снижение прибыли при росте выручки.
        if (
            bool(r.has_prev_period)
            and r.revenue_prev is not None
            and r.gross_profit_prev is not None
        ):
            rev_growth = safe_ratio(D(r.revenue) - D(r.revenue_prev), D(r.revenue_prev))
            gp_prev = D(r.gross_profit_prev)
            gp_change = (
                safe_ratio(D(r.gross_profit) - gp_prev, abs(gp_prev)) if gp_prev != 0 else None
            )
            if (
                rev_growth is not None
                and rev_growth > 0
                and gp_change is not None
                and gp_change < -settings.gp_drop_share
            ):
                out.append(
                    _rec(
                        r,
                        "R5",
                        "Средняя",
                        "Прибыль снижается при росте выручки",
                        "Сравнение с предыдущим периодом той же длины",
                        f"Выручка {_pct(rev_growth)} к прошлому периоду, валовая прибыль {_pct(gp_change)}",
                        "Рост себестоимости, увеличение скидок, смещение продаж в акционные позиции",
                        "Проверить маржу, размер скидок и структуру продаж по точкам",
                        "Сравнение двух соседних периодов чувствительно к сезонности и промоакциям",
                    )
                )
    cols = [
        "rule",
        "severity",
        "product_id",
        "sku",
        "product_name",
        "category_name",
        "problem",
        "basis",
        "value",
        "possible_cause",
        "action",
        "limitations",
    ]
    df = pd.DataFrame(out, columns=cols)
    if not df.empty:
        df = df.sort_values(
            ["severity", "rule", "product_id"],
            key=lambda s: s.map(SEVERITY_ORDER) if s.name == "severity" else s,
        ).reset_index(drop=True)
    return df


RULE_TITLES = {
    "R1": "Высокая выручка и низкая маржа",
    "R2": "Стабильный спрос и частое отсутствие",
    "R3": "Высокие списания",
    "R4": "Низкий вклад и нестабильный спрос",
    "R5": "Прибыль падает при росте выручки",
}
