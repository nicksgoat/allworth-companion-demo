-- ============================================================================
-- Allworth Executive Reporting – Page View Analytics Table
-- Target: Azure Synapse dedicated SQL pool (DataWarehouse)
-- Schema: aip
-- ============================================================================

-- Ensure the schema exists
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'aip')
    EXEC('CREATE SCHEMA aip');
GO

-- Create table (HEAP – no clustered index; use CTAS to add later if needed)
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'aip' AND TABLE_NAME = 'page_views'
)
CREATE TABLE aip.page_views (
    [id]              INT IDENTITY(1,1)   NOT NULL,
    [timestamp]       DATETIME2           NOT NULL,
    [page]            NVARCHAR(500)       NULL,
    [referrer]        NVARCHAR(1000)      NULL,
    [user_agent]      NVARCHAR(1000)      NULL,
    [ip_address]      NVARCHAR(45)        NULL,
    [screen_width]    INT                 NULL,
    [screen_height]   INT                 NULL,
    [window_width]    INT                 NULL,
    [window_height]   INT                 NULL,
    [load_time_ms]    INT                 NULL,
    [is_embedded]     BIT                 NULL,
    [timezone]        NVARCHAR(100)       NULL,
    [language]        NVARCHAR(20)        NULL,
    [user_email]      NVARCHAR(320)       NULL
);
GO

-- If the table already exists, add the user_email column:
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'aip' AND TABLE_NAME = 'page_views' AND COLUMN_NAME = 'user_email'
)
ALTER TABLE aip.page_views ADD [user_email] NVARCHAR(320) NULL;
GO

-- Useful queries:

-- Total views & unique visitors
-- SELECT COUNT(*) AS total_views,
--        COUNT(DISTINCT ip_address) AS unique_visitors
-- FROM aip.page_views;

-- Daily breakdown (last 30 days)
-- SELECT CAST([timestamp] AS DATE) AS visit_date,
--        COUNT(*) AS views,
--        COUNT(DISTINCT ip_address) AS unique_visitors
-- FROM aip.page_views
-- WHERE [timestamp] >= DATEADD(day, -30, GETUTCDATE())
-- GROUP BY CAST([timestamp] AS DATE)
-- ORDER BY visit_date DESC;


