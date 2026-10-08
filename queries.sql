-- name: Revenue by category
SELECT p.category,
       COUNT(DISTINCT o.order_id)              AS orders,
       ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue
FROM order_items i
JOIN orders   o ON o.order_id   = i.order_id
JOIN products p ON p.product_id = i.product_id
WHERE o.status <> 'cancelled'
GROUP BY p.category
ORDER BY revenue DESC;

-- name: Top 3 customers by revenue in each city (window function)
WITH customer_revenue AS (
    SELECT c.customer_id, c.city,
           ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue
    FROM customers c
    JOIN orders o      ON o.customer_id = c.customer_id
    JOIN order_items i ON i.order_id    = o.order_id
    WHERE o.status <> 'cancelled'
    GROUP BY c.customer_id, c.city
), ranked AS (
    SELECT *, RANK() OVER (PARTITION BY city ORDER BY revenue DESC) AS city_rank
    FROM customer_revenue
)
SELECT city, city_rank, customer_id, revenue
FROM ranked
WHERE city_rank <= 3
ORDER BY city, city_rank
LIMIT 12;

-- name: Monthly revenue with running total (window function)
WITH monthly AS (
    SELECT SUBSTR(o.order_date, 1, 7) AS month,
           ROUND(SUM(i.quantity * i.unit_price), 2) AS revenue
    FROM orders o
    JOIN order_items i ON i.order_id = o.order_id
    WHERE o.status <> 'cancelled'
    GROUP BY month
)
SELECT month, revenue,
       ROUND(SUM(revenue) OVER (ORDER BY month), 2) AS running_total
FROM monthly
ORDER BY month
LIMIT 12;

-- name: Average delivery days by city
SELECT c.city,
       ROUND(AVG(julianday(o.delivery_date) - julianday(o.order_date)), 1) AS avg_delivery_days,
       COUNT(*) AS delivered_orders
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.status = 'delivered' AND o.delivery_date IS NOT NULL
GROUP BY c.city
ORDER BY avg_delivery_days;

-- name: Order status mix
SELECT status,
       COUNT(*) AS orders,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM orders
GROUP BY status
ORDER BY orders DESC;
