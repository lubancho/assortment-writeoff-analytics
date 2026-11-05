"""ABC-анализ (документ 04, раздел 3).

Простыми словами: сортируем товары по вкладу (выручке или валовой прибыли) от большего к меньшему
и копим долю. Пока накопленная доля ДО товара меньше 80% — товар в классе A, до 95% — B, дальше — C.

Правила, которые важно помнить:
- выручка и прибыль классифицируются ОТДЕЛЬНО, классы не смешиваются;
- при равенстве значений порядок — по product_id по возрастанию (результат воспроизводим);
- товар, на котором накопленная доля переходит границу, остаётся в «старшем» классе;
- товары с вкладом ≤ 0 — класс C с пометкой; в знаменатель долей они не входят;
- класс — не основание для вывода товара из ассортимента.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

ZERO = Decimal(0)


@dataclass(frozen=True)
class AbcThresholds:
    a: Decimal = Decimal("0.80")
    b: Decimal = Decimal("0.95")

    def errors(self) -> list[str]:
        if not (ZERO < self.a < self.b < Decimal(1)):
            return ["Пороги должны удовлетворять условию 0 < A < B < 100%"]
        return []


def classify(values: pd.DataFrame, thresholds: AbcThresholds | None = None) -> pd.DataFrame:
    """values: колонки product_id, value (Decimal). Возвращает share, cum_before, cum_share, abc_class, note."""
    thresholds = thresholds or AbcThresholds()
    if thresholds.errors():
        raise ValueError(thresholds.errors()[0])
    df = values[["product_id", "value"]].copy()
    df["value"] = df["value"].map(lambda v: v if isinstance(v, Decimal) else Decimal(str(v)))
    df = df.sort_values(
        ["value", "product_id"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    positive_total = sum((v for v in df["value"] if v > 0), ZERO)
    shares, cum_before, cum_after, classes, notes = [], [], [], [], []
    cum = ZERO
    for v in df["value"]:
        if v <= 0 or positive_total <= 0:
            shares.append(None)
            cum_before.append(None)
            cum_after.append(None)
            classes.append("C")
            notes.append("нет продаж" if v == 0 else "отрицательный вклад")
            continue
        share = v / positive_total
        before = cum
        cum += share
        shares.append(share)
        cum_before.append(before)
        cum_after.append(cum)
        classes.append("A" if before < thresholds.a else "B" if before < thresholds.b else "C")
        notes.append("")
    df["share"], df["cum_before"], df["cum_share"] = shares, cum_before, cum_after
    df["abc_class"], df["note"] = classes, notes
    return df


def summary(classified: pd.DataFrame) -> pd.DataFrame:
    """Сколько товаров и какая доля вклада в каждом классе."""
    rows = []
    for cls in ("A", "B", "C"):
        part = classified[classified["abc_class"] == cls]
        rows.append(
            {
                "abc_class": cls,
                "products": len(part),
                "value": sum(part["value"], ZERO),
                "share": sum((s for s in part["share"] if s is not None), ZERO),
            }
        )
    return pd.DataFrame(rows)
