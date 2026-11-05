# 07. SQL-задачи 1–10

Документ собран автоматически из шапок файлов `src/asa/sql/*.sql` — описание и запрос всегда совпадают. Число строк — фактический результат на демо-данных за период 04.10–31.10.2026 с параметрами по умолчанию.

Запустить любой запрос: `asa sql <номер> --from 2026-10-04 --to 2026-10-31` или экран «Отчёты».

| № | Задача | JOIN | GROUP BY | CTE | Оконные функции | Строк в результате |
|---|---|---|---|---|---|---|
| 1 | Выручка по торговым точкам | да | да | да | да | 15 |
| 2 | Выручка по категориям | да | да | да | да | 5 |
| 3 | Валовая прибыль по SKU | да | да | — | — | 150 |
| 4 | Маржинальность по точкам | да | да | да | да | 15 |
| 5 | Динамика продаж по дням | да | да | да | да | 28 |
| 6 | Товары без продаж за период | да | да | да | — | 0 (по точкам: 8) |
| 7 | Товары с высоким уровнем списаний | да | да | да | — | 60 |
| 8 | ABC-классификация | да | да | да | да | 150 |
| 9 | Сравнение текущего и предыдущего периодов | да | да | да | — | 5 |
| 10 | Топ товаров по прибыли | да | да | да | да | 10 |

## 1. Выручка по торговым точкам

Файл: `src/asa/sql/01_revenue_by_store.sql`

- Цель:        сравнить точки по выручке, числу чеков и среднему чеку за период.
- Таблицы:     core.sale_line (строки чеков), core.store.
- Соединение:  store LEFT JOIN агрегат продаж — точки без продаж попадают в результат с нулём.
- Детализация: одна строка = одна торговая точка.
- Результат:   выручка (с учётом скидок и возвратов, без отмен), чеки, средний чек, доля в сети.
- Проверка:    сумма revenue по всем точкам = выручке сети за период (тест test_sql_tasks_add_up).

```sql
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
```

## 2. Выручка по категориям

Файл: `src/asa/sql/02_revenue_by_category.sql`

- Цель:        вклад каждой категории в выручку сети.
- Таблицы:     core.sale_line, core.product (категория товара), core.category.
- Соединение:  sale_line → product по product_id → category; категории без продаж — через LEFT JOIN.
- Детализация: одна строка = одна категория.
- Результат:   выручка, проданные единицы (нетто), доля категории в выручке (оконная функция).
- Проверка:    сумма долей = 1; сумма выручки = выручке сети.

```sql
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
```

## 3. Валовая прибыль по SKU

Файл: `src/asa/sql/03_gross_profit_by_sku.sql`

- Цель:        прибыльность каждого товара в целом по сети.
- Таблицы:     core.v_sale_fact (строки продаж + себестоимость на дату продажи), core.product, core.category.
- Соединение:  v_sale_fact уже содержит себестоимость, найденную по интервалу действия версии
  (sale_date BETWEEN valid_from AND valid_to); здесь — только справочники.
- Детализация: одна строка = один товар (SKU).
- Результат:   выручка, выручка с известной себестоимостью, себестоимость продаж, валовая прибыль,
  маржинальность. Строки без себестоимости на дату не участвуют в прибыли (документ 04).
- Проверка:    сумма gross_profit по SKU = валовой прибыли сети; совпадает с расчётом Python.

```sql
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
```

## 4. Маржинальность по точкам

Файл: `src/asa/sql/04_margin_by_store.sql`

- Цель:        найти точки с самой низкой валовой маржинальностью.
- Таблицы:     core.v_sale_fact, core.store.
- Соединение:  v_sale_fact → store по store_id.
- Детализация: одна строка = одна точка.
- Результат:   выручка, валовая прибыль, маржинальность, место по маржинальности (RANK),
  отклонение от маржинальности сети в процентных пунктах.
- Проверка:    маржинальность сети считается как отношение сумм, а не как среднее по точкам.

```sql
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
```

## 5. Динамика продаж по дням

Файл: `src/asa/sql/05_daily_sales.sql`

- Цель:        ежедневная выручка и количество с недельной скользящей средней.
- Таблицы:     core.sale_line; generate_series — календарь периода.
- Соединение:  календарь LEFT JOIN продажи по дате — дни без продаж видны как 0, а не пропадают.
- Детализация: одна строка = один день.
- Результат:   выручка, проданные единицы (нетто), чеки, скользящая средняя выручки за 7 дней.
- Проверка:    число строк = числу дней периода; сумма выручки = выручке сети.

```sql
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
```

## 6. Товары без продаж за период

Файл: `src/asa/sql/06_products_without_sales.sql`

- Цель:        найти активные товары, которые не продавались, и отличить «не покупали» от «не было в продаже».
- Таблицы:     core.product, core.sale_line, core.stock_daily (признак is_available).
- Соединение:  product LEFT JOIN агрегат продаж; отдельно — число дней, когда товар был в продаже.
- Детализация: одна строка = один товар (в целом по сети) или пара «точка × товар» при %(by_store)s = true.
- Результат:   товары с нулевыми чистыми продажами; доступные дни; вывод «не было в продаже» или «не покупали».
- Проверка:    товар с продажами в любой точке не попадает в сетевой список; при by_store — проверка по паре.

```sql
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
```

## 7. Товары с высоким уровнем списаний

Файл: `src/asa/sql/07_high_write_offs.sql`

- Цель:        найти товары, у которых большая доля выпущенной продукции уходит в списание.
- Таблицы:     mart.v_write_off_fact (списания + себестоимость на дату), core.v_sale_fact.
- Соединение:  два агрегата по product_id (списания и продажи) соединяются FULL JOIN,
  чтобы не потерять товар, у которого есть только списания.
- Детализация: одна строка = один товар в целом по сети.
- Результат:   себестоимость продаж, стоимость списаний, доля списаний =
  списания / (себестоимость продаж + списания), т. е. доля в себестоимости выпуска.
- Проверка:    доля от 0 до 1; товары с долей ниже %(threshold)s не выводятся.

```sql
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
```

## 8. ABC-классификация

Файл: `src/asa/sql/08_abc.sql`

- Цель:        разделить товары по вкладу в выручку или валовую прибыль (%(metric)s).
- Таблицы:     core.v_sale_fact, core.product.
- Соединение:  product LEFT JOIN агрегат — товары без продаж тоже классифицируются (класс C).
- Детализация: одна строка = один товар в целом по сети.
- Порядок:     по значению показателя по убыванию, при равенстве — по product_id по возрастанию.
- Граница:     товар относится к классу, в котором начинается его вклад: если накопленная доля
  ДО этого товара меньше порога A, товар — A (даже если с ним накопленная доля перешла порог).
  Неположительный вклад: товары с показателем ≤ 0 — класс C, в знаменатель долей не входят.
- Результат:   значение, доля, накопленная доля до и после товара, класс.
- Проверка:    совпадает с Python-реализацией asa.abc (тест test_abc_sql_matches_python).

```sql
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
```

## 9. Сравнение текущего и предыдущего периодов

Файл: `src/asa/sql/09_period_comparison.sql`

- Цель:        как изменились выручка и валовая прибыль категорий по сравнению с предыдущим
  периодом той же длины.
- Таблицы:     core.v_sale_fact, core.category.
- Соединение:  одна выборка за оба периода; разделение условными агрегатами FILTER.
- Детализация: одна строка = одна категория.
- Результат:   выручка и прибыль за текущий и предыдущий периоды, абсолютное и относительное изменение.
- Проверка:    предыдущий период = [d0 − (d1 − d0 + 1); d0 − 1], без пересечения с текущим.

```sql
WITH bounds AS (
    SELECT %(d0)s::date AS d0, %(d1)s::date AS d1,
           %(d0)s::date - (%(d1)s::date - %(d0)s::date + 1) AS p0, %(d0)s::date - 1 AS p1
), agg AS (
    SELECT f.category_id,
           sum(f.net_revenue) FILTER (WHERE f.sale_date BETWEEN b.d0 AND b.d1) AS rev_cur,
           sum(f.net_revenue) FILTER (WHERE f.sale_date BETWEEN b.p0 AND b.p1) AS rev_prev,
           sum(f.net_revenue - f.net_cogs) FILTER (WHERE f.sale_date BETWEEN b.d0 AND b.d1
                                                     AND f.unit_cost IS NOT NULL) AS gp_cur,
           sum(f.net_revenue - f.net_cogs) FILTER (WHERE f.sale_date BETWEEN b.p0 AND b.p1
                                                     AND f.unit_cost IS NOT NULL) AS gp_prev
    FROM core.v_sale_fact f CROSS JOIN bounds b
    WHERE f.sale_date BETWEEN b.p0 AND b.d1
    GROUP BY f.category_id
)
SELECT c.category_id, c.name AS category_name,
       a.rev_cur, a.rev_prev, a.rev_cur - a.rev_prev AS rev_change,
       (a.rev_cur - a.rev_prev) / NULLIF(a.rev_prev, 0) AS rev_change_pct,
       a.gp_cur, a.gp_prev, a.gp_cur - a.gp_prev AS gp_change,
       (a.gp_cur - a.gp_prev) / NULLIF(abs(a.gp_prev), 0) AS gp_change_pct
FROM core.category c LEFT JOIN agg a ON a.category_id = c.category_id
ORDER BY c.category_id;
```

## 10. Топ товаров по прибыли

Файл: `src/asa/sql/10_top_products_by_profit.sql`

- Цель:        N самых прибыльных товаров сети и их место внутри своей категории.
- Таблицы:     core.v_sale_fact, core.product, core.category.
- Соединение:  агрегат по товару → справочники.
- Детализация: одна строка = один товар; выводятся первые %(top)s мест.
- Результат:   валовая прибыль, место в сети (RANK — при равенстве одинаковое место),
  место в категории (оконная функция с PARTITION BY), доля в прибыли категории.
- Проверка:    места идут без пропусков при отсутствии равных значений; доли в категории ≤ 1.

```sql
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
```
