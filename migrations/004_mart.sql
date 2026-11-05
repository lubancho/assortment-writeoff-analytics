-- Аналитические представления проекта №2.

-- Списания с себестоимостью на дату списания.
CREATE VIEW mart.v_write_off_fact AS
SELECT w.write_off_id,
       w.write_off_date,
       w.store_id,
       w.product_id,
       p.category_id,
       w.reason,
       w.quantity,
       c.unit_cost,
       w.quantity * c.unit_cost AS cost_amount
FROM core.write_off w
JOIN core.product p ON p.product_id = w.product_id
LEFT JOIN core.v_product_cost_range c
       ON c.product_id = w.product_id
      AND w.write_off_date BETWEEN c.valid_from AND c.valid_to;

-- Остатки с себестоимостью на дату и признаком «распродано».
CREATE VIEW mart.v_stock_fact AS
SELECT s.store_id,
       s.product_id,
       p.category_id,
       p.is_fresh,
       s.stock_date,
       s.opening_qty,
       s.produced_qty,
       s.sold_qty,
       s.written_off_qty,
       s.closing_qty,
       s.is_available,
       cal.is_open,
       c.unit_cost,
       (s.opening_qty + s.produced_qty) * c.unit_cost AS available_value,
       s.closing_qty * c.unit_cost                    AS closing_value,
       -- Распродано: товар был в продаже, продажи были, а к концу дня не осталось ничего
       -- (для свежей продукции — ничего не ушло в списание «истёк срок»).
       (s.is_available AND s.sold_qty > 0
        AND s.opening_qty + s.produced_qty - s.sold_qty - COALESCE(r.returned_qty, 0) <= 0) AS is_sold_out
FROM core.stock_daily s
JOIN core.product p ON p.product_id = s.product_id
JOIN core.store_calendar cal ON cal.store_id = s.store_id AND cal.calendar_date = s.stock_date
LEFT JOIN (
    SELECT store_id, product_id, write_off_date, sum(quantity) AS returned_qty
    FROM core.write_off WHERE reason = 'return'
    GROUP BY store_id, product_id, write_off_date
) r ON r.store_id = s.store_id AND r.product_id = s.product_id AND r.write_off_date = s.stock_date
LEFT JOIN core.v_product_cost_range c
       ON c.product_id = s.product_id
      AND s.stock_date BETWEEN c.valid_from AND c.valid_to;
