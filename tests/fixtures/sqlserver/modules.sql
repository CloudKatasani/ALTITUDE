-- SalesDW module script (views, functions, procedures, triggers), scripted per object with GO separators.
-- Used by tests/fixtures/sqlserver/estate.py to populate an emulated sys.sql_modules.

CREATE FUNCTION dbo.fn_FiscalQuarter (@d DATE)
RETURNS TINYINT
AS
BEGIN
    -- fiscal year starts in July
    RETURN CASE WHEN MONTH(@d) BETWEEN 7 AND 9 THEN 1
                WHEN MONTH(@d) BETWEEN 10 AND 12 THEN 2
                WHEN MONTH(@d) BETWEEN 1 AND 3 THEN 3
                ELSE 4 END;
END
GO

CREATE FUNCTION dbo.fn_GetRegion (@StoreKey INT)
RETURNS NVARCHAR(50)
AS
BEGIN
    DECLARE @r NVARCHAR(50);
    SELECT @r = r.RegionName
    FROM dbo.DimStore s
    JOIN dbo.Region r ON r.RegionKey = s.RegionKey
    WHERE s.StoreKey = @StoreKey;
    RETURN @r;
END
GO

CREATE FUNCTION dbo.fn_CustomerOrders (@CustomerKey INT)
RETURNS TABLE
AS
RETURN (
    SELECT f.OrderNumber, f.OrderDate, f.Amount
    FROM dbo.FactSales f
    WHERE f.CustomerKey = @CustomerKey
);
GO

CREATE VIEW dbo.vw_SalesBase
AS
SELECT *
FROM dbo.FactSales f
JOIN dbo.DimDate d ON d.DateKey = f.DateKey;
GO

CREATE VIEW dbo.vw_SalesSummary
AS
SELECT b.CalendarYear, b.CalendarMonth, b.StoreKey, b.CustomerKey, SUM(b.Amount) AS Amount, COUNT(*) AS Orders
FROM dbo.vw_SalesBase b
GROUP BY b.CalendarYear, b.CalendarMonth, b.StoreKey, b.CustomerKey;
GO

CREATE VIEW dbo.vw_SalesSummaryRegion
AS
SELECT s.CalendarYear, s.CalendarMonth, dbo.fn_GetRegion(s.StoreKey) AS RegionName, SUM(s.Amount) AS Amount
FROM dbo.vw_SalesSummary s
GROUP BY s.CalendarYear, s.CalendarMonth, dbo.fn_GetRegion(s.StoreKey);
GO

CREATE VIEW rpt.vw_ExecDashboard
AS
SELECT DISTINCT r.CalendarYear, r.CalendarMonth, r.RegionName, r.Amount, t.TargetAmount
FROM dbo.vw_SalesSummaryRegion r
LEFT JOIN dbo.SalesTarget t ON t.RegionName = r.RegionName AND t.CalendarYear = r.CalendarYear
GROUP BY r.CalendarYear, r.CalendarMonth, r.RegionName, r.Amount, t.TargetAmount;
GO

CREATE VIEW rpt.vw_SalesByRegion
AS
SELECT rg.RegionName, d.CalendarYear, SUM(f.Amount) AS Amount
FROM dbo.FactSales f WITH (NOLOCK)
JOIN dbo.DimStore s ON s.StoreKey = f.StoreKey
JOIN dbo.Region rg ON rg.RegionKey = s.RegionKey
JOIN dbo.DimDate d ON d.DateKey = f.DateKey
GROUP BY rg.RegionName, d.CalendarYear;
GO

CREATE VIEW rpt.vw_CustomerSales
AS
SELECT c.CustomerKey, c.CustomerName, c.Segment, s.CalendarYear, SUM(s.Amount) AS Amount
FROM dbo.vw_SalesSummary s
JOIN dbo.DimCustomer c ON c.CustomerKey = s.CustomerKey
GROUP BY c.CustomerKey, c.CustomerName, c.Segment, s.CalendarYear;
GO

CREATE VIEW rpt.vw_InventoryStatus
AS
SELECT p.ProductName, st.StoreName, i.OnHandQty, i.SnapshotDate
FROM dbo.FactInventory i
JOIN dbo.DimProduct p ON p.ProductKey = i.ProductKey
JOIN dbo.DimStore st ON st.StoreKey = i.StoreKey
WHERE i.SnapshotDate = (SELECT MAX(SnapshotDate) FROM dbo.FactInventory);
GO

CREATE VIEW rpt.vw_Returns
AS
SELECT r.ReturnDate, p.ProductName, r.Quantity, r.Reason
FROM dbo.FactReturns r
JOIN dbo.DimProduct p ON p.ProductKey = r.ProductKey;
GO

CREATE VIEW rpt.vw_ProductMargin
AS
SELECT p.ProductName, pr.PromotionName, p.ListPrice - p.StandardCost AS Margin
FROM dbo.DimProduct p, dbo.Promotion pr;
GO

CREATE VIEW rpt.vw_CustomerPII
AS
SELECT c.CustomerKey, c.CustomerName, a.Email, a.Phone, a.PostalCode
FROM dbo.DimCustomer c
JOIN dbo.CustomerAddress a ON a.CustomerKey = c.CustomerKey
WHERE UPPER(a.Country) = 'US' AND CONVERT(VARCHAR(8), c.CreatedDate, 112) >= '20200101';
GO

CREATE VIEW rpt.vw_MonthEnd
AS
SELECT m.PeriodKey, m.RegionName, m.Revenue, m.Returns, m.ClosedAt
FROM rpt.MonthEndClose m;
GO

CREATE VIEW dbo.vw_LegacyBudget
AS
SELECT b.FiscalYear, b.CostCenter, b.BudgetAmount
FROM dbo.OldBudget2018 b;
GO

CREATE PROCEDURE etl.usp_LogLoad
    @ProcName SYSNAME,
    @Rows INT,
    @Status VARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO audit.LoadLog (ProcName, RowsAffected, Status, LoggedAt)
    VALUES (@ProcName, @Rows, @Status, SYSDATETIME());
END
GO

CREATE PROCEDURE etl.usp_LoadDimCustomer
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;
        MERGE dbo.DimCustomer AS tgt
        USING stg.Customer_Load AS src
            ON tgt.CustomerCode = src.CustomerCode
        WHEN MATCHED AND (tgt.CustomerName <> src.CustomerName OR tgt.Segment <> src.Segment) THEN
            UPDATE SET tgt.CustomerName = src.CustomerName, tgt.Segment = src.Segment, tgt.UpdatedDate = GETDATE()
        WHEN NOT MATCHED BY TARGET THEN
            INSERT (CustomerCode, CustomerName, Segment, CreatedDate)
            VALUES (src.CustomerCode, src.CustomerName, src.Segment, GETDATE());
        DECLARE @rows INT = @@ROWCOUNT;
        INSERT INTO dbo.CustomerAddress (CustomerKey, Email, Phone, PostalCode, Country)
        SELECT c.CustomerKey, s.Email, s.Phone, s.PostalCode, s.Country
        FROM stg.Customer_Load s
        JOIN dbo.DimCustomer c ON c.CustomerCode = s.CustomerCode
        WHERE NOT EXISTS (SELECT 1 FROM dbo.CustomerAddress a WHERE a.CustomerKey = c.CustomerKey);
        COMMIT TRANSACTION;
        EXEC etl.usp_LogLoad 'usp_LoadDimCustomer', @rows, 'OK';
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        INSERT INTO audit.ErrorLog (ProcName, ErrorNumber, ErrorMessage, LoggedAt)
        VALUES ('usp_LoadDimCustomer', ERROR_NUMBER(), ERROR_MESSAGE(), SYSDATETIME());
        THROW;
    END CATCH
END
GO

CREATE PROCEDURE etl.usp_LoadDimProduct
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @code NVARCHAR(20), @name NVARCHAR(100), @cost MONEY, @price MONEY;
    DECLARE product_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT ProductCode, ProductName, StandardCost, ListPrice FROM stg.Product_Load;
    BEGIN TRY
        OPEN product_cursor;
        FETCH NEXT FROM product_cursor INTO @code, @name, @cost, @price;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            IF EXISTS (SELECT 1 FROM dbo.DimProduct WHERE ProductCode = @code)
                UPDATE dbo.DimProduct
                SET ProductName = @name, StandardCost = @cost, ListPrice = @price
                WHERE ProductCode = @code;
            ELSE
                INSERT INTO dbo.DimProduct (ProductCode, ProductName, StandardCost, ListPrice)
                VALUES (@code, @name, @cost, @price);
            FETCH NEXT FROM product_cursor INTO @code, @name, @cost, @price;
        END
        CLOSE product_cursor;
        DEALLOCATE product_cursor;
        EXEC etl.usp_LogLoad 'usp_LoadDimProduct', 0, 'OK';
    END TRY
    BEGIN CATCH
        IF CURSOR_STATUS('local', 'product_cursor') >= 0
        BEGIN
            CLOSE product_cursor;
            DEALLOCATE product_cursor;
        END
        RAISERROR('DimProduct load failed', 16, 1);
    END CATCH
END
GO

CREATE PROCEDURE etl.usp_LoadFactSales
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        TRUNCATE TABLE dbo.FactSales;
        INSERT INTO dbo.FactSales
        SELECT *
        FROM stg.Sales_Load;
        DECLARE @rows INT = @@ROWCOUNT;
        IF @@ERROR <> 0
            RAISERROR('FactSales reload failed', 16, 1);
        EXEC etl.usp_LogLoad 'usp_LoadFactSales', @rows, 'OK';
    END TRY
    BEGIN CATCH
        INSERT INTO audit.ErrorLog (ProcName, ErrorNumber, ErrorMessage, LoggedAt)
        VALUES ('usp_LoadFactSales', ERROR_NUMBER(), ERROR_MESSAGE(), SYSDATETIME());
        THROW;
    END CATCH
END
GO

CREATE PROCEDURE etl.usp_LoadFactInventory
    @SnapshotDate DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @sql NVARCHAR(MAX);
    DECLARE @partition NVARCHAR(8) = CONVERT(NVARCHAR(8), ISNULL(@SnapshotDate, CAST(GETDATE() AS DATE)), 112);
    SET @sql = N'DELETE FROM dbo.FactInventory WHERE SnapshotDate = ''' + @partition + N''';'
             + N'INSERT INTO dbo.FactInventory (ProductKey, StoreKey, OnHandQty, SnapshotDate) '
             + N'SELECT ProductKey, StoreKey, OnHandQty, SnapshotDate FROM stg.Inventory_Load_' + @partition;
    EXEC sp_executesql @sql;
    EXEC etl.usp_LogLoad 'usp_LoadFactInventory', @@ROWCOUNT, 'OK';
END
GO

CREATE PROCEDURE etl.usp_LoadFactReturns
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @id INT = (SELECT MIN(ReturnId) FROM stg.Returns_Load);
    WHILE @id IS NOT NULL
    BEGIN
        INSERT INTO dbo.FactReturns (ReturnId, ProductKey, ReturnDate, Quantity, Reason)
        SELECT r.ReturnId, p.ProductKey, r.ReturnDate, r.Quantity, r.Reason
        FROM stg.Returns_Load r
        JOIN dbo.DimProduct p ON p.ProductCode = r.ProductCode
        WHERE r.ReturnId = @id;
        SELECT @id = MIN(ReturnId) FROM stg.Returns_Load WHERE ReturnId > @id;
    END
    EXEC etl.usp_LogLoad 'usp_LoadFactReturns', 0, 'OK';
END
GO

CREATE PROCEDURE etl.usp_MonthEndClose
    @PeriodKey INT
AS
BEGIN
    SET NOCOUNT ON;
    IF @PeriodKey IS NULL
    BEGIN
        RAISERROR('PeriodKey is required', 16, 1);
        RETURN;
    END
    DELETE FROM rpt.MonthEndClose WHERE PeriodKey = @PeriodKey;
    INSERT INTO rpt.MonthEndClose (PeriodKey, RegionName, Revenue, Returns, ClosedAt)
    SELECT @PeriodKey, rg.RegionName, SUM(f.Amount), ISNULL(SUM(r.Quantity), 0), GETDATE()
    FROM dbo.FactSales f
    JOIN dbo.DimStore s ON s.StoreKey = f.StoreKey
    JOIN dbo.Region rg ON rg.RegionKey = s.RegionKey
    LEFT JOIN dbo.FactReturns r ON r.ProductKey = f.ProductKey AND r.ReturnDate = f.OrderDate
    WHERE f.DateKey / 100 = @PeriodKey
    GROUP BY rg.RegionName;
    EXEC etl.usp_LogLoad 'usp_MonthEndClose', @@ROWCOUNT, 'OK';
END
GO

CREATE PROCEDURE etl.usp_RegulatoryFiling
    @PeriodKey INT
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @sql NVARCHAR(MAX) = N'INSERT INTO rpt.RegulatoryFiling (PeriodKey, RegionName, Revenue, FiledAt) '
        + N'SELECT PeriodKey, RegionName, Revenue, GETDATE() FROM rpt.MonthEndClose WHERE PeriodKey = '
        + CAST(@PeriodKey AS NVARCHAR(10));
    BEGIN TRY
        EXEC (@sql);
    END TRY
    BEGIN CATCH
        INSERT INTO audit.ErrorLog (ProcName, ErrorNumber, ErrorMessage, LoggedAt)
        VALUES ('usp_RegulatoryFiling', ERROR_NUMBER(), ERROR_MESSAGE(), SYSDATETIME());
        THROW;
    END CATCH
END
GO

CREATE PROCEDURE dbo.usp_GetCustomerOrders
    @CustomerKey INT,
    @Year INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT DISTINCT f.OrderNumber, f.OrderDate, SUM(f.Amount) AS Amount
    FROM dbo.FactSales f
    WHERE f.CustomerKey = @CustomerKey
      AND YEAR(f.OrderDate) = @Year
    GROUP BY f.OrderNumber, f.OrderDate;
END
GO

CREATE PROCEDURE dbo.usp_SearchCustomers
    @Name NVARCHAR(100),
    @Segment NVARCHAR(50) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @sql NVARCHAR(MAX) = N'SELECT CustomerKey, CustomerName, Segment FROM dbo.DimCustomer WHERE CustomerName LIKE ''%' + @Name + N'%''';
    IF @Segment IS NOT NULL
        SET @sql = @sql + N' AND Segment = ''' + @Segment + N'''';
    EXEC sp_executesql @sql;
END
GO

CREATE PROCEDURE dbo.usp_RefreshExchangeRates
AS
BEGIN
    SET NOCOUNT ON;
    TRUNCATE TABLE dbo.ExchangeRate;
    INSERT INTO dbo.ExchangeRate (CurrencyCode, RateDate, Rate)
    SELECT CurrencyCode, RateDate, Rate
    FROM FXSRV.Treasury.dbo.DailyRates;
END
GO

CREATE PROCEDURE dbo.usp_Old_ReconcileBudget
AS
BEGIN
    DECLARE @cc VARCHAR(20), @amt MONEY;
    DECLARE c CURSOR FOR SELECT CostCenter, BudgetAmount FROM dbo.OldBudget2018;
    OPEN c;
    FETCH NEXT FROM c INTO @cc, @amt;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        UPDATE dbo.FactBudget SET ActualAmount = @amt WHERE CostCenter = @cc;
        FETCH NEXT FROM c INTO @cc, @amt;
    END
    CLOSE c;
    DEALLOCATE c;
END
GO

CREATE PROCEDURE dbo.usp_FixSalesData_2019
AS
BEGIN
    -- one-off data fix from the 2019 POS outage
    UPDATE dbo.tmp_SalesFix SET Amount = Amount * -1 WHERE Amount < 0;
    INSERT INTO dbo.FactSales_Archive SELECT * FROM dbo.tmp_SalesFix;
END
GO

CREATE PROCEDURE etl.usp_ArchiveSales
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO dbo.FactSales_Archive
    SELECT f.*
    FROM dbo.FactSales f
    CROSS JOIN dbo.DimDate d
    WHERE d.DateKey = f.DateKey AND d.CalendarYear < YEAR(GETDATE()) - 7;
END
GO

CREATE TRIGGER dbo.trg_FactSales_Audit ON dbo.FactSales
AFTER UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO audit.SalesAudit (OrderNumber, Action, ChangedAt)
    SELECT d.OrderNumber, CASE WHEN EXISTS (SELECT 1 FROM inserted) THEN 'U' ELSE 'D' END, GETDATE()
    FROM deleted d;
END
GO
