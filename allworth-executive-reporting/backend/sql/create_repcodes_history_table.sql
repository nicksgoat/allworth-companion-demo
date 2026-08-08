-- ============================================================================
-- Allworth Rep Codes — change-history / audit table
-- Target: Azure Synapse dedicated SQL pool (DataWarehouse)
-- Schema: tho
--
-- WHY THIS EXISTS
--   tho.repcodes only stores the *current* state of each row plus who/when it
--   was last touched (modified_by/modified_at). Every UPDATE/DELETE/bulk-upsert
--   overwrites in place, so a mistaken edit or a bad import is unrecoverable
--   short of a full warehouse restore. Synapse dedicated pools do NOT support
--   temporal tables (SYSTEM_VERSIONING) or triggers, so history must be written
--   by the application layer (backend/repcodes/history.py) inside the same
--   transaction as each write.
--
-- WHAT IT STORES
--   One row per change, holding the FULL row image that RESULTED from the
--   operation (the "after-image"):
--     - INSERT   -> the new values
--     - UPDATE   -> the post-update values
--     - DELETE   -> the last-known values, captured just before deletion
--     - RESTORE  -> the values written by a rollback (so rollbacks are auditable)
--     - BASELINE -> one snapshot per pre-existing row at first deploy (below)
--   Rollback = copy a chosen history row's column values back onto the live row
--   (re-inserting with IDENTITY_INSERT if the row had been deleted).
--
-- Keep the column list in sync with create_repcodes_table.sql and
-- repcodes/routes.py (EDITABLE_COLUMNS) and repcodes/history.py (_DDL).
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'tho')
    EXEC('CREATE SCHEMA tho');
GO

IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'tho' AND TABLE_NAME = 'repcodes_history'
)
CREATE TABLE tho.repcodes_history (
    [history_id]                    INT IDENTITY(1,1) NOT NULL,
    [repcode_id]                    INT             NOT NULL,
    [operation]                     NVARCHAR(10)    NOT NULL,  -- INSERT|UPDATE|DELETE|RESTORE|BASELINE
    [batch_id]                      NVARCHAR(36)    NULL,      -- groups a bulk import / multi-row op
    [source]                        NVARCHAR(20)    NULL,      -- ui | bulk | seed
    [custodian]                     NVARCHAR(100)   NULL,
    [actively_used]                 BIT             NULL,
    [wrap_fee_type]                 NVARCHAR(100)   NULL,
    [for_employee_accounts]         BIT             NULL,
    [fidelity_g_number]             NVARCHAR(50)    NULL,
    [g_number_usage]                NVARCHAR(255)   NULL,
    [description]                   NVARCHAR(500)   NULL,
    [notes]                         NVARCHAR(2000)  NULL,
    [schwab_master_account]         NVARCHAR(50)    NULL,
    [master_account_type]           NVARCHAR(100)   NULL,
    [allworth_advisor]              NVARCHAR(255)   NULL,
    [allworth_office]               NVARCHAR(255)   NULL,
    [separate_account_manager]      NVARCHAR(255)   NULL,
    [sma_strategy]                  NVARCHAR(255)   NULL,
    [other_third_party]             NVARCHAR(255)   NULL,
    [american_funds_rep_number]     NVARCHAR(50)    NULL,
    [american_funds_branch_number]  NVARCHAR(50)    NULL,
    [bloomwell_529_rep_code]        NVARCHAR(50)    NULL,
    [changed_by]                    NVARCHAR(320)   NULL,
    [changed_at]                    DATETIME2       NOT NULL
)
WITH (
    -- Append-only log: ROUND_ROBIN avoids the per-write REPLICATE rebuild cost.
    DISTRIBUTION = ROUND_ROBIN,
    HEAP
);
GO

-- ============================================================================
-- Baseline backfill
-- Give every row that already exists a single starting snapshot so the very
-- first edit/delete of a legacy (seeded) row is still recoverable. Runs only
-- once, while the history table is empty.
-- ============================================================================
IF NOT EXISTS (SELECT TOP 1 1 FROM tho.repcodes_history)
BEGIN
    INSERT INTO tho.repcodes_history (
        [repcode_id], [operation], [batch_id], [source],
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts],
        [fidelity_g_number], [g_number_usage], [description], [notes],
        [schwab_master_account], [master_account_type], [allworth_advisor],
        [allworth_office], [separate_account_manager], [sma_strategy],
        [other_third_party], [american_funds_rep_number],
        [american_funds_branch_number], [bloomwell_529_rep_code],
        [changed_by], [changed_at]
    )
    SELECT
        [repcode_id], N'BASELINE', NULL, N'seed',
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts],
        [fidelity_g_number], [g_number_usage], [description], [notes],
        [schwab_master_account], [master_account_type], [allworth_advisor],
        [allworth_office], [separate_account_manager], [sma_strategy],
        [other_third_party], [american_funds_rep_number],
        [american_funds_branch_number], [bloomwell_529_rep_code],
        COALESCE([modified_by], N'system (baseline)'),
        COALESCE([modified_at], SYSUTCDATETIME())
    FROM tho.repcodes;
END
GO
