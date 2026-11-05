-- Задача 6. Товары без продаж за период.
-- Цель:        найти активные товары, которые не продавались, и отличить «не покупали» от «не было в продаже».
-- Таблицы:     core.product, core.sale_line, core.stock_daily (признак is_available).
-- Соединение:  product LEFT JOIN агрегат продаж; отдельно — число дней, когда товар был в продаже.
-- Детализация: одна строка = один товар (в целом по сети) или пара «точка × товар» при %(by_store)s = true.
-- Результат:   товары с нулевыми чистыми продажами; доступные дни; вывод «не было в продаже» или «не покупали».
-- Проверка:    товар с продажами в любой точке не попадает в сетевой список; при by_store — проверка по паре.
WITH grid AS (
    SELECT CASE WHEN %(by_store)s THEN s.store_id END AS store_id, p.product_id
    FROM core.product p
    CROSS JOIN (SELECT store_id FROM core.store WHERE is_active
                UNION ALL SELECT NULL WHERE NOT %(by_store)s) s
    WHERE p.is_active AND (s.store_id IS NOT NULL) = %(by_store)s
), sold AS (
    SELECT CASE WHEN %(by_store)s THEN store_id END AS store_id, product_id, sum(net_quantity) AS net_qty
    FROM core.sale_line
    WHERE sale_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY 1, 2
), avail AS (
    SELECT CASE WHEN %(by_store)s THEN store_id END AS store_id, product_id,
           count(*) FILTER (WHERE is_available) AS available_days,
           count(*)                            AS days
    FROM core.stock_daily
    WHERE stock_date BETWEEN %(d0)s AND %(d1)s
    GROUP BY 1, 2
)
SELECT g.store_id, st.name AS store_name, p.product_id, p.sku, p.name AS product_name, c.name AS category_name,
       COALESCE(s.net_qty, 0)        AS net_qty,
       COALESCE(a.available_days, 0) AS available_days,
       COALESCE(a.days, 0)           AS days,
       CASE WHEN COALESCE(a.available_days, 0) = 0 THEN 'не было в продаже'
            ELSE 'был в продаже, но не покупали' END AS interpretation
FROM grid g
JOIN core.product p ON p.product_id = g.product_id
JOIN core.category c ON c.category_id = p.category_id
LEFT JOIN core.store st ON st.store_id = g.store_id
LEFT JOIN sold s  ON s.product_id = g.product_id AND s.store_id IS NOT DISTINCT FROM g.store_id
LEFT JOIN avail a ON a.product_id = g.product_id AND a.store_id IS NOT DISTINCT FROM g.store_id
WHERE COALESCE(s.net_qty, 0) <= 0
ORDER BY g.store_id NULLS FIRST, p.product_id;
