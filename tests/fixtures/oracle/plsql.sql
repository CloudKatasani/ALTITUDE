CREATE OR REPLACE PACKAGE SALES.SALES_PKG AS
  g_batch_id NUMBER;            -- package state (OR-04)
  PROCEDURE load_daily(p_day IN DATE DEFAULT TRUNC(SYSDATE) - 1);
  PROCEDURE log_error(p_msg IN VARCHAR2);
END sales_pkg;
/
CREATE OR REPLACE PACKAGE BODY SALES.SALES_PKG AS
  PROCEDURE log_error(p_msg IN VARCHAR2) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
  BEGIN
    INSERT INTO SALES.ERR_LOG (logged_at, message) VALUES (SYSDATE, p_msg);
    COMMIT;
  END log_error;

  PROCEDURE load_daily(p_day IN DATE DEFAULT TRUNC(SYSDATE) - 1) IS
    TYPE t_orders IS TABLE OF SALES.STG_ORDERS%ROWTYPE;
    l_orders t_orders;
    CURSOR c_stg IS
      SELECT * FROM SALES.STG_ORDERS WHERE order_date = p_day;
  BEGIN
    g_batch_id := g_batch_id + 1;
    OPEN c_stg;
    LOOP
      FETCH c_stg BULK COLLECT INTO l_orders LIMIT 1000;
      EXIT WHEN l_orders.COUNT = 0;
      FOR i IN 1 .. l_orders.COUNT LOOP
        INSERT INTO SALES.ORDERS (order_id, customer_id, order_date, status)
        VALUES (l_orders(i).order_id, l_orders(i).customer_id, l_orders(i).order_date, NVL(l_orders(i).status, ''));
      END LOOP;
    END LOOP;
    CLOSE c_stg;
    DELETE FROM SALES.DAILY_SALES_AGG WHERE sales_day = p_day;
    INSERT INTO SALES.DAILY_SALES_AGG (sales_day, product_id, amount)
    SELECT o.order_date, l.product_id, SUM(l.quantity * l.unit_price)
    FROM SALES.ORDERS o, SALES.ORDER_LINES l
    WHERE l.order_id (+) = o.order_id
      AND o.order_date = p_day
    GROUP BY o.order_date, l.product_id;
    EXECUTE IMMEDIATE 'ANALYZE TABLE SALES.DAILY_SALES_AGG COMPUTE STATISTICS';
    COMMIT;
  EXCEPTION
    WHEN OTHERS THEN
      log_error(SQLERRM);
      RAISE;
  END load_daily;
END sales_pkg;
/
CREATE OR REPLACE PACKAGE FIN.GL_CLOSE_PKG AS
  PROCEDURE close_period(p_period IN DATE);
END gl_close_pkg;
/
CREATE OR REPLACE PACKAGE BODY FIN.GL_CLOSE_PKG AS
  PROCEDURE close_period(p_period IN DATE) IS
  BEGIN
    DELETE FROM FIN.GL_PERIOD_CLOSE WHERE period_start = TRUNC(p_period, 'MM');
    INSERT INTO FIN.GL_PERIOD_CLOSE (period_start, account_id, balance, closed_at)
    SELECT TRUNC(p_period, 'MM'), g.account_id, SUM(g.amount), SYSDATE
    FROM FIN.GL_ENTRIES g
    WHERE g.entry_date < ADD_MONTHS(TRUNC(p_period, 'MM'), 1)
    GROUP BY g.account_id;
    COMMIT;
  END close_period;
END gl_close_pkg;
/
CREATE OR REPLACE FUNCTION SALES.FN_NET_AMOUNT(p_gross IN NUMBER, p_tax_rate IN NUMBER) RETURN NUMBER IS
BEGIN
  RETURN ROUND(p_gross / (1 + NVL(p_tax_rate, 0)), 2);
END;
/
CREATE OR REPLACE PROCEDURE SALES.PURGE_OLD_ORDERS AS
  CURSOR c_old IS SELECT order_id FROM SALES.ORDERS_HIST_2015;
BEGIN
  FOR r IN c_old LOOP
    DELETE FROM SALES.ORDERS_HIST_2015 WHERE order_id = r.order_id;
  END LOOP;
  COMMIT;
END;
/
CREATE OR REPLACE TRIGGER SALES.TRG_ORDERS_AUDIT
AFTER UPDATE OR DELETE ON SALES.ORDERS
FOR EACH ROW
BEGIN
  INSERT INTO SALES.ORDERS_AUDIT (order_id, action, changed_at)
  VALUES (:OLD.order_id, CASE WHEN UPDATING THEN 'U' ELSE 'D' END, SYSDATE);
END;
/
