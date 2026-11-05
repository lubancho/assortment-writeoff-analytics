-- Задача 4. Маржинальность по точкам.
-- Цель:        найти точки с самой низкой валовой маржинальностью.
-- Таблицы:     core.v_sale_fact, core.store.
-- Соединение:  v_sale_fact → store по store_id.
-- Детализация: одна строка = одна точка.
-- Результат:   выручка, валовая прибыль, маржинальность, место по маржинальности (RANK),
--              отклонение от маржинальности сети в процентных пунктах.
-- Проверка:    маржинальность сети считается как отношение сумм, а не как среднее по точкам.
WITH by_store AS (
    SELECT f.store_id,
           sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL)                   AS revenue_costed,
           sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL) - sum(f.net_cogs) AS gross_profit
    FROM core.v_sale_fact f
    WHERE f.sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY f.store_id
)
SELECT s.store_id,
       s.name                                              AS store_name,
       b.revenue_costed,
       b.gross_profit,
       b.gross_profit / NULLIF(b.revenue_costed, 0)        AS gross_margin,
       RANK() OVER (ORDER BY b.gross_profit / NULLIF(b.revenue_costed, 0) DESC NULLS LAST) AS margin_rank,
       b.gross_profit / NULLIF(b.revenue_costed, 0)
         - sum(b.gross_profit) OVER () / NULLIF(sum(b.revenue_costed) OVER (), 0)        AS diff_from_network
FROM core.store s
JOIN by_store b ON b.store_id = s.store_id
ORDER BY margin_rank;
