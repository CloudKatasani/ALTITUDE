CREATE OR REPLACE PACKAGE BODY sales_pkg AS
  g_batch_id NUMBER;

  PROCEDURE close_period(p_period IN VARCHAR2) IS
    CURSOR c_open IS SELECT order_id FROM orders WHERE period = p_period AND status = 'OPEN';
  BEGIN
    FOR r IN c_open LOOP
      UPDATE orders SET status = 'CLOSED' WHERE order_id = r.order_id;
    END LOOP;
    DBMS_OUTPUT.PUT_LINE('closed ' || p_period);
  END close_period;
END sales_pkg;
/

CREATE OR REPLACE TRIGGER trg_orders_audit
BEFORE UPDATE ON orders
FOR EACH ROW
BEGIN
  :NEW.updated_at := SYSDATE;
END;
/

SELECT o.order_id, NVL(c.customer_name, 'UNKNOWN') AS customer_name, SYSDATE AS extracted_at
FROM orders o, customers c
WHERE o.customer_id = c.customer_id(+);

SELECT order_id, amount FROM orders WHERE ROWNUM <= 100;

CREATE TABLE order_archive (
  order_id NUMBER(12) NOT NULL,
  amount NUMBER,
  closed_on DATE
);
