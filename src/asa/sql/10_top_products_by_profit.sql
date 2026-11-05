-- Задача 10. Топ товаров по прибыли.
-- Цель:        N самых прибыльных товаров сети и их место внутри своей категории.
-- Таблицы:     core.v_sale_fact, core.product, core.category.
-- Соединение:  агрегат по товару → справочники.
-- Детализация: одна строка = один товар; выводятся первые %(top)s мест.
-- Результат:   валовая прибыль, место в сети (RANK — при равенстве одинаковое место),
--              место в категории (оконная функция с PARTITION BY), доля в прибыли категории.
-- Проверка:    места идут без пропусков при отсутствии равных значений; доли в категории ≤ 1.
WITH gp AS (
    SELECT f.product_id, p.category_id,
           sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL) - sum(f.net_cogs) AS gross_profit,
           sum(f.net_revenue) AS revenue
    FROM core.v_sale_fact f JOIN core.product p ON p.product_id = f.product_id
    WHERE f.sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY f.product_id, p.category_id
), ranked AS (
    SELECT gp.*,
           RANK() OVER (ORDER BY gross_profit DESC NULLS LAST)                          AS network_rank,
           RANK() OVER (PARTITION BY category_id ORDER BY gross_profit DESC NULLS LAST) AS category_rank,
           gross_profit / NULLIF(sum(gross_profit) OVER (PARTITION BY category_id), 0)  AS category_share
    FROM gp
)
SELECT r.network_rank, r.product_id, p.sku, p.name AS product_name, c.name AS category_name,
       r.revenue, r.gross_profit, r.category_rank, r.category_share
FROM ranked r
JOIN core.product p ON p.product_id = r.product_id
JOIN core.category c ON c.category_id = r.category_id
WHERE r.network_rank <= %(top)s
ORDER BY r.network_rank, r.product_id;
