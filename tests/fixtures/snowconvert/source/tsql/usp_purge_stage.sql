CREATE PROCEDURE [dbo].[usp_purge_stage] AS
BEGIN
    SET NOCOUNT ON;
    DELETE FROM dbo.stg_orders WHERE load_date < DATEADD(day, -30, GETDATE());
    INSERT INTO dbo.etl_log (step_name, rows_affected, logged_at)
    VALUES ('purge_stage', @@ROWCOUNT, GETDATE());
END
GO

SELECT TOP 50 o.order_id, ISNULL(o.discount, 0) AS discount, CONVERT(VARCHAR(10), o.order_date, 120) AS order_day
FROM dbo.orders o WITH (NOLOCK)
WHERE o.status = 'SHIPPED';
GO

CREATE TRIGGER trg_orders_ins ON dbo.orders AFTER INSERT AS
BEGIN
    INSERT INTO dbo.order_audit (order_id, action) SELECT order_id, 'INSERT' FROM inserted;
END
GO

DECLARE order_cursor CURSOR FOR SELECT order_id FROM #pending_orders;
