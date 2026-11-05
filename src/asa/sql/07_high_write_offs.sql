-- Задача 7. Товары с высоким уровнем списаний.
-- Цель:        найти товары, у которых большая доля выпущенной продукции уходит в списание.
-- Таблицы:     mart.v_write_off_fact (списания + себестоимость на дату), core.v_sale_fact.
-- Соединение:  два агрегата по product_id (списания и продажи) соединяются FULL JOIN,
--              чтобы не потерять товар, у которого есть только списания.
-- Детализация: одна строка = один товар в целом по сети.
-- Результат:   себестоимость продаж, стоимость списаний, доля списаний =
--              списания / (себестоимость продаж + списания), т. е. доля в себестоимости выпуска.
-- Проверка:    доля от 0 до 1; товары с долей ниже %(threshold)s не выводятся.
WITH wo AS (
    SELECT product_id, sum(quantity) AS write_off_qty, sum(cost_amount) AS write_off_cost
    FROM mart.v_write_off_fact
    WHERE write_off_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY product_id
), sales AS (
    SELECT product_id, sum(net_cogs) AS cogs, sum(net_quantity) AS net_qty
    FROM core.v_sale_fact
    WHERE sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY product_id
), joined AS (
    SELECT COALESCE(w.product_id, s.product_id) AS product_id,
           COALESCE(w.write_off_qty, 0) AS write_off_qty, COALESCE(w.write_off_cost, 0) AS write_off_cost,
           COALESCE(s.cogs, 0) AS cogs, COALESCE(s.net_qty, 0) AS net_qty
    FROM wo w FULL JOIN sales s ON s.product_id = w.product_id
)
SELECT j.product_id, p.sku, p.name AS product_name, c.name AS category_name, p.is_fresh,
       j.net_qty, j.write_off_qty, j.cogs, j.write_off_cost,
       j.write_off_cost / NULLIF(j.cogs + j.write_off_cost, 0) AS write_off_share
FROM joined j
JOIN core.product p ON p.product_id = j.product_id
JOIN core.category c ON c.category_id = p.category_id
WHERE j.write_off_cost / NULLIF(j.cogs + j.write_off_cost, 0) >= %(threshold)s
ORDER BY write_off_share DESC, j.product_id;
