-- Задача 5. Динамика продаж по дням.
-- Цель:        ежедневная выручка и количество с недельной скользящей средней.
-- Таблицы:     core.sale_line; generate_series — календарь периода.
-- Соединение:  календарь LEFT JOIN продажи по дате — дни без продаж видны как 0, а не пропадают.
-- Детализация: одна строка = один день.
-- Результат:   выручка, проданные единицы (нетто), чеки, скользящая средняя выручки за 7 дней.
-- Проверка:    число строк = числу дней периода; сумма выручки = выручке сети.
WITH days AS (
    SELECT d::date AS sale_date
    FROM generate_series(%(d0)s::date, %(d1)s::date, interval '1 day') AS d
), sales AS (
    SELECT sale_date,
           sum(net_revenue)  AS revenue,
           sum(net_quantity) AS net_qty,
           count(DISTINCT order_id) FILTER (WHERE NOT is_cancelled AND operation_type = 'sale') AS orders
    FROM core.sale_line
    WHERE sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY sale_date
)
SELECT d.sale_date,
       COALESCE(s.revenue, 0) AS revenue,
       COALESCE(s.net_qty, 0) AS net_qty,
       COALESCE(s.orders, 0)  AS orders,
       avg(COALESCE(s.revenue, 0)) OVER (ORDER BY d.sale_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
                              AS revenue_ma7
FROM days d
LEFT JOIN sales s ON s.sale_date = d.sale_date
ORDER BY d.sale_date;
