-- Задача 9. Сравнение текущего и предыдущего периодов.
-- Цель:        как изменились выручка и валовая прибыль категорий по сравнению с предыдущим
--              периодом той же длины.
-- Таблицы:     core.v_sale_fact, core.category.
-- Соединение:  одна выборка за оба периода; разделение условными агрегатами FILTER.
-- Детализация: одна строка = одна категория.
-- Результат:   выручка и прибыль за текущий и предыдущий периоды, абсолютное и относительное изменение.
-- Проверка:    предыдущий период = [d0 − (d1 − d0 + 1); d0 − 1], без пересечения с текущим.
WITH bounds AS (
    SELECT %(d0)s::date AS d0, %(d1)s::date AS d1,
           %(d0)s::date - (%(d1)s::date - %(d0)s::date + 1) AS p0, %(d0)s::date - 1 AS p1
), agg AS (
    SELECT f.category_id,
           sum(f.net_revenue) FILTER (WHERE f.sale_date BETWEEN b.d0 AND b.d1) AS rev_cur,
           sum(f.net_revenue) FILTER (WHERE f.sale_date BETWEEN b.p0 AND b.p1) AS rev_prev,
           sum(f.net_revenue - f.net_cogs) FILTER (WHERE f.sale_date BETWEEN b.d0 AND b.d1
                                                     AND f.unit_cost IS NOT NULL) AS gp_cur,
           sum(f.net_revenue - f.net_cogs) FILTER (WHERE f.sale_date BETWEEN b.p0 AND b.p1
                                                     AND f.unit_cost IS NOT NULL) AS gp_prev
    FROM core.v_sale_fact f CROSS JOIN bounds b
    WHERE f.sale_date BETWEEN b.p0 AND b.d1
    GROUP BY f.category_id
)
SELECT c.category_id, c.name AS category_name,
       a.rev_cur, a.rev_prev, a.rev_cur - a.rev_prev AS rev_change,
       (a.rev_cur - a.rev_prev) / NULLIF(a.rev_prev, 0) AS rev_change_pct,
       a.gp_cur, a.gp_prev, a.gp_cur - a.gp_prev AS gp_change,
       (a.gp_cur - a.gp_prev) / NULLIF(abs(a.gp_prev), 0) AS gp_change_pct
FROM core.category c LEFT JOIN agg a ON a.category_id = c.category_id
ORDER BY c.category_id;
