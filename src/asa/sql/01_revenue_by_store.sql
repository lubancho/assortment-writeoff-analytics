-- Задача 1. Выручка по торговым точкам.
-- Цель:        сравнить точки по выручке, числу чеков и среднему чеку за период.
-- Таблицы:     core.sale_line (строки чеков), core.store.
-- Соединение:  store LEFT JOIN агрегат продаж — точки без продаж попадают в результат с нулём.
-- Детализация: одна строка = одна торговая точка.
-- Результат:   выручка (с учётом скидок и возвратов, без отмен), чеки, средний чек, доля в сети.
-- Проверка:    сумма revenue по всем точкам = выручке сети за период (тест test_sql_tasks_add_up).
WITH sales AS (
    SELECT store_id,
           sum(net_revenue)                                          AS revenue,
           count(DISTINCT order_id) FILTER (WHERE NOT is_cancelled
                                             AND operation_type = 'sale') AS orders
    FROM core.sale_line
    WHERE sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY store_id
)
SELECT s.store_id,
       s.name                                        AS store_name,
       s.city,
       COALESCE(x.revenue, 0)                        AS revenue,
       COALESCE(x.orders, 0)                         AS orders,
       x.revenue / NULLIF(x.orders, 0)               AS avg_check,
       COALESCE(x.revenue, 0) / NULLIF(sum(x.revenue) OVER (), 0) AS revenue_share
FROM core.store s
LEFT JOIN sales x ON x.store_id = s.store_id
ORDER BY revenue DESC, s.store_id;
