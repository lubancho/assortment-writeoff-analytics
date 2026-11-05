"""XYZ-анализ стабильности спроса (документ 04, раздел 4).

Простыми словами: для каждого товара берём продажи по неделям и считаем коэффициент вариации
CV = стандартное отклонение / среднее. Чем меньше CV, тем ровнее спрос: X — стабильный,
Y — колеблющийся, Z — нестабильный.

Что учитываем отдельно (ТЗ §23):
- только полные недели (понедельник–воскресенье) внутри периода;
- неделя, в которой товар был доступен меньше чем в 80% рабочих «точко-дней», исключается:
  низкие продажи в ней могут означать отсутствие товара, а не низкий спрос;
- меньше 6 пригодных недель — класс не присваивается («недостаточно наблюдений»);
- товар появился позже начала периода — «недостаточная история»;
- нет продаж ни в одной пригодной неделе — «нет продаж»;
- сезонность: по желанию CV считается по отклонениям от линейного тренда.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class XyzSettings:
    x_max: float = 0.10
    y_max: float = 0.25
    min_weeks: int = 6
    min_availability: float = 0.80
    detrend: bool = False

    def errors(self) -> list[str]:
        errs = []
        if not (0 < self.x_max < self.y_max):
            errs.append("Пороги должны удовлетворять условию 0 < X < Y")
        if self.min_weeks < 3:
            errs.append("Минимум недель — не меньше 3")
        if not (0 < self.min_availability <= 1):
            errs.append("Порог доступности — от 0 до 100%")
        return errs


def full_weeks(d0: date, d1: date) -> tuple[date, date] | None:
    """Первая и последняя даты полных недель (пн–вс) внутри периода."""
    start = d0 + timedelta(days=(7 - d0.weekday()) % 7)
    end = d1 - timedelta(days=(d1.weekday() + 1) % 7)
    if end < start + timedelta(days=6):
        return None
    return start, end


def coefficient_of_variation(values: np.ndarray, detrend: bool = False) -> float | None:
    """CV по генеральной совокупности (ddof=0). None, если среднее ≤ 0."""
    values = np.asarray(values, dtype=float)
    mean = values.mean() if len(values) else 0.0
    if len(values) == 0 or mean <= 0:
        return None
    if detrend and len(values) >= 3:
        x = np.arange(len(values))
        slope, intercept = np.polyfit(x, values, 1)
        residuals = values - (slope * x + intercept)
        return float(residuals.std(ddof=0) / mean)
    return float(values.std(ddof=0) / mean)


def classify(
    weekly: pd.DataFrame,
    settings: XyzSettings | None = None,
    first_sale: dict | None = None,
    period_start: date | None = None,
) -> pd.DataFrame:
    """weekly: product_id, week_start, net_qty (float), availability (доля 0..1).

    Возвращает по товару: weeks_used, weeks_excluded, mean, cv, xyz_class, note.
    """
    settings = settings or XyzSettings()
    if settings.errors():
        raise ValueError(settings.errors()[0])
    rows = []
    for pid, grp in weekly.groupby("product_id", sort=True):
        grp = grp.sort_values("week_start")
        usable = grp[grp["availability"] >= settings.min_availability]
        qty = usable["net_qty"].astype(float).to_numpy()
        note, cls, cv = "", None, None
        if (
            first_sale
            and period_start
            and first_sale.get(pid)
            and first_sale[pid] > period_start + timedelta(days=13)
        ):
            note = "недостаточная история"
        elif len(qty) < settings.min_weeks:
            note = "недостаточно наблюдений"
        elif qty.sum() <= 0:
            note = "нет продаж"
        else:
            cv = coefficient_of_variation(qty, settings.detrend)
            cls = "X" if cv <= settings.x_max else "Y" if cv <= settings.y_max else "Z"
        rows.append(
            {
                "product_id": pid,
                "weeks_used": len(qty),
                "weeks_excluded": len(grp) - len(usable),
                "mean_weekly": float(qty.mean()) if len(qty) else 0.0,
                "cv": cv,
                "xyz_class": cls,
                "note": note,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "product_id",
            "weeks_used",
            "weeks_excluded",
            "mean_weekly",
            "cv",
            "xyz_class",
            "note",
        ],
    )
