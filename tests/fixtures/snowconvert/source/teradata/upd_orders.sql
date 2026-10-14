-- Apply late-arriving order status changes
UPDATE ord FROM stg.order_status s
SET status_code = s.status_code
WHERE ord.order_id = s.order_id;

COLLECT STATS ON edw.fact_orders COLUMN (order_id);
