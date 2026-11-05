-- Задача 2. Выручка по категориям.
-- Цель:        вклад каждой категории в выручку сети.
-- Таблицы:     core.sale_line, core.product (категория товара), core.category.
-- Соединение:  sale_line → product по product_id → category; категории без продаж — через LEFT JOIN.
-- Детализация: одна строка = одна категория.
-- Результат:   выручка, проданные единицы (нетто), доля категории в выручке (оконная функция).
-- Проверка:    сумма долей = 1; сумма выручки = выручке сети.
WITH sales AS (
    SELECT p.category_id,
           sum(s.net_revenue)  AS revenue,
           sum(s.net_quantity) AS net_qty
    FROM core.sale_line s
    JOIN core.product p ON p.product_id = s.product_id
    WHERE s.sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY p.category_id
)
SELECT c.category_id,
       c.name                                                    AS category_name,
       COALESCE(x.revenue, 0)                                    AS revenue,
       COALESCE(x.net_qty, 0)                                    AS net_qty,
       COALESCE(x.revenue, 0) / NULLIF(sum(x.revenue) OVER (), 0) AS revenue_share
FROM core.category c
LEFT JOIN sales x ON x.category_id = c.category_id
ORDER BY revenue DESC;
