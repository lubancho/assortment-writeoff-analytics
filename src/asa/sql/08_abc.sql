-- Задача 8. ABC-классификация.
-- Цель:        разделить товары по вкладу в выручку или валовую прибыль (%(metric)s).
-- Таблицы:     core.v_sale_fact, core.product.
-- Соединение:  product LEFT JOIN агрегат — товары без продаж тоже классифицируются (класс C).
-- Детализация: одна строка = один товар в целом по сети.
-- Порядок:     по значению показателя по убыванию, при равенстве — по product_id по возрастанию.
-- Граница:     товар относится к классу, в котором начинается его вклад: если накопленная доля
--              ДО этого товара меньше порога A, товар — A (даже если с ним накопленная доля перешла порог).
-- Неположительный вклад: товары с показателем ≤ 0 — класс C, в знаменатель долей не входят.
-- Результат:   значение, доля, накопленная доля до и после товара, класс.
-- Проверка:    совпадает с Python-реализацией asa.abc (тест test_abc_sql_matches_python).
WITH v AS (
    SELECT p.product_id,
           CASE WHEN %(metric)s = 'gross_profit'
                THEN COALESCE(sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL), 0)
                     - COALESCE(sum(f.net_cogs), 0)
                ELSE COALESCE(sum(f.net_revenue), 0) END AS value
    FROM core.product p
    LEFT JOIN core.v_sale_fact f ON f.product_id = p.product_id AND f.sale_date BETWEEN %(d0)s AND %(d1)s
    WHERE p.is_active
    GROUP BY p.product_id
), shares AS (
    SELECT product_id, value,
           CASE WHEN value > 0 THEN value / sum(value) FILTER (WHERE value > 0) OVER () END AS share
    FROM v
), cum AS (
    SELECT product_id, value, share,
           sum(share) OVER (ORDER BY value DESC, product_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             AS cum_share
    FROM shares
)
SELECT c.product_id, p.sku, p.name AS product_name, c.value, c.share,
       c.cum_share - c.share AS cum_before, c.cum_share,
       CASE WHEN c.value <= 0 THEN 'C'
            WHEN c.cum_share - c.share < %(a)s THEN 'A'
            WHEN c.cum_share - c.share < %(b)s THEN 'B'
            ELSE 'C' END AS abc_class
FROM cum c JOIN core.product p ON p.product_id = c.product_id
ORDER BY c.value DESC, c.product_id;
