-- Задача 3. Валовая прибыль по SKU.
-- Цель:        прибыльность каждого товара в целом по сети.
-- Таблицы:     core.v_sale_fact (строки продаж + себестоимость на дату продажи), core.product, core.category.
-- Соединение:  v_sale_fact уже содержит себестоимость, найденную по интервалу действия версии
--              (sale_date BETWEEN valid_from AND valid_to); здесь — только справочники.
-- Детализация: одна строка = один товар (SKU).
-- Результат:   выручка, выручка с известной себестоимостью, себестоимость продаж, валовая прибыль,
--              маржинальность. Строки без себестоимости на дату не участвуют в прибыли (документ 04).
-- Проверка:    сумма gross_profit по SKU = валовой прибыли сети; совпадает с расчётом Python.
SELECT p.product_id,
       p.sku,
       p.name                                                           AS product_name,
       c.name                                                           AS category_name,
       COALESCE(sum(f.net_revenue), 0)                                  AS revenue,
       COALESCE(sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL), 0) AS revenue_costed,
       COALESCE(sum(f.net_cogs), 0)                                     AS cogs,
       COALESCE(sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL), 0)
         - COALESCE(sum(f.net_cogs), 0)                                 AS gross_profit,
       (sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL) - sum(f.net_cogs))
         / NULLIF(sum(f.net_revenue) FILTER (WHERE f.unit_cost IS NOT NULL), 0) AS gross_margin
FROM core.product p
JOIN core.category c ON c.category_id = p.category_id
LEFT JOIN core.v_sale_fact f
       ON f.product_id = p.product_id
      AND f.sale_date BETWEEN %(d0)s AND %(d1)s
GROUP BY p.product_id, p.sku, p.name, c.name
ORDER BY gross_profit DESC, p.product_id;
