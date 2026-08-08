-- ============================================================================
-- Allworth Rep Codes Consolidated lookup table
-- Target: Azure Synapse dedicated SQL pool (DataWarehouse)
-- Schema: tho
-- Source seed: c:\Users\Mark.Fanning\workspace\repcodes.csv
-- Row count at seed time: 933
--
-- This script is idempotent for the CREATE TABLE step but the INSERT will
-- duplicate rows if re-run. Guard the INSERT manually if reseeding.
-- ============================================================================

IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'tho')
    EXEC('CREATE SCHEMA tho');
GO

IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'tho' AND TABLE_NAME = 'repcodes'
)
CREATE TABLE tho.repcodes (
    [repcode_id]                  INT IDENTITY(1,1) NOT NULL,
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
    [modified_by]                   NVARCHAR(320)   NULL,
    [modified_at]                   DATETIME2           NULL
)
WITH (
    DISTRIBUTION = REPLICATE,
    HEAP
);
GO

-- ============================================================================
-- Seed data
-- Only inserted if the table is empty (safe to re-run after the initial load).
-- Synapse dedicated SQL pool does NOT support multi-row VALUES; we use
-- INSERT ... SELECT ... UNION ALL ..., batched at 200 rows per statement.
-- ============================================================================
IF NOT EXISTS (SELECT TOP 1 1 FROM tho.repcodes)
BEGIN
    INSERT INTO tho.repcodes (
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts], [fidelity_g_number], [g_number_usage], [description], [notes], [schwab_master_account], [master_account_type], [allworth_advisor], [allworth_office], [separate_account_manager], [sma_strategy], [other_third_party], [american_funds_rep_number], [american_funds_branch_number], [bloomwell_529_rep_code]
    )
    SELECT N'Fidelity', 1, N'Wrap', 0, N'G15458553', N'Primary', N'Allworth - General Market', N'Allworth Master (ABP) (Tamarac feed) Use "Allworth Financial" as Primary Advisor', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G15240550', N'Secondary', N'Allworth - General Market', N'Allworth Fee Master (REQUIRED to BILL) Use "Allworth Financial"', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G14362946', N'Brokeragelink', N'Allworth - General Market (EPPA)', N'Brokeragelink Master, Use "Allworth Financial" as Primary Advisor', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G07622966', N'Primary', N'AW Airline', N'AW Airline Master, Use "AW Airline" as Primary Authorized Agent/Advisor', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G14531912', N'Brokeragelink', N'AW Airline (EPPA)', N'AW Airline Brokeragelink, Use "AW Airline" as Primary Authorized Agent/Advisor', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G41854792', N'Primary', N'Allworth Private Client', N'For Restricted Employee Accounts', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G13566212', N'Brokeragelink', N'The Pacific Financial Grp', N'TPFG, Use "The Pacific Financial Group" as Primary Authorization Agent/Advisor', NULL, NULL, NULL, NULL, NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G33125972', N'Secondary', N'Chicago Office - Diana Law Guardian', N'Only for Diana Law guardian accounts for her access | 4th or 5th G Number', NULL, NULL, NULL, N'Riverwoods', NULL, NULL, N'Diana Law', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G33125973', N'Secondary', N'Chicago Office - Diana Law TTEE', N'Only for Diana Law trustee accounts for her access | 4th or 5th G Number', NULL, NULL, NULL, N'Riverwoods', NULL, NULL, N'Diana Law', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32395724', N'Secondary', N'Chicago Office - ImpactAsset DAF', N'For Dual Imports into Addepar', NULL, NULL, NULL, N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G18632230', N'Secondary', N'Tax-Exempt Market/AFS', N'TEM - Tax-Exempt Market/AFS', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G38081391', N'Secondary', N'Tristate Capital Bank', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11817432', NULL, N'RAA', N'Hot-money', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G18446040', NULL, N'RAA', N'AFS (Jeff''s company)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G18632229', NULL, N'RAA', N'RNav (Fred Knieb company)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20500376', NULL, N'RAA', N'RNav (Fred Knieb company)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20500377', NULL, N'RAA', N'RNav (Fred Knieb company)', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14397322', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G24551818', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12514643', NULL, N'Ktrade', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12030375', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515313', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14525749', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534271', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14542022', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14571436', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14588826', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14724184', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14724185', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14866985', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14937629', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15092445', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15270531', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835124', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835125', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835126', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835127', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835128', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835129', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835130', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835131', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835132', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15835133', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15893506', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967443', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967444', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967445', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967448', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967450', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16382663', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G18754287', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G23756252', NULL, N'Allworth', N'might be TAMP G#', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G10884184', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11413192', NULL, N'Ktrade', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11573184', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11991509', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12009622', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12108385', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12177197', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G13376017', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14149445', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14397309', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14842905', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16131451', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G17673913', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12163487', NULL, N'Ktrade', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14025846', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14219270', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14406343', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534827', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15850889', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20721783', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G28874827', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12203529', NULL, N'Ktrade', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534835', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G12310504', NULL, N'Ktrade', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G29494904', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G13274058', NULL, N'Ktrade', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G13062895', NULL, N'RAA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967447', NULL, N'Allworth', N'no accounts', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14301925', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14397313', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14397317', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515311', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515316', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515318', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515320', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515322', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14515324', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14525747', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14525751', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527239', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527241', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527243', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527245', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527247', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527249', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14527254', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14528284', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14528286', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14528288', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14529457', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14529655', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14529657', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14529659', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14529661', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14531906', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14531907', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14531908', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14531918', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534267', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534268', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534269', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14534270', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14538106', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14538107', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14542023', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14542025', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14542184', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14545431', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14553554', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14591416', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14633246', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14657887', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14657888', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14672415', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14676001', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14677080', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14678433', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14680505', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14694843', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14701459', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14701468', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14707268', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14716045', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14724183', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14732261', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14732262', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14743580', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14762996', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14778401', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14796968', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14801202', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14810672', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14831291', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14852054', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14852325', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14856457', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14856458', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14856459', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14870593', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14872619', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14911506', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14911507', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14933741', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14933742', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14933743', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14937630', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14937631', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G14943918', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15013723', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15042520', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15085295', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15085296', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15098746', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15101986', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15101987', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15142097', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15142104', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15145903', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15147002', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15160473', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15207845', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15239758', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15239759', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15266379', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15297769', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15297770', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15299479', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15366380', NULL, N'Hanson McClain', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967446', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967449', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15967451', NULL, N'Allworth''s PCRA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16382662', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16382664', NULL, N'Allworth', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16403464', NULL, N'Advisors Group', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33993304', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Peter Abi-Nader', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33263568', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Benjamin Abraham', N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G38350559', N'Advisor G Number (Secondary)', N'AEF Donor  Clearwater Analytics - Integration Exchange', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887617', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Chuck Alexander', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33993305', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'David Bastoni', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33993306', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jeffrey Baumert', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887618', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jessica Baumgartner', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33993307', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Stephanie Bemerer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007897', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bob Benyamin', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007898', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Amy Bertle', N'Denver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007899', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Davis Blomquist', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345946', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Bogard', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093549', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Victoria Bogner', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345948', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Leonardo Bojorquez', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL;

    INSERT INTO tho.repcodes (
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts], [fidelity_g_number], [g_number_usage], [description], [notes], [schwab_master_account], [master_account_type], [allworth_advisor], [allworth_office], [separate_account_manager], [sma_strategy], [other_third_party], [american_funds_rep_number], [american_funds_branch_number], [bloomwell_529_rep_code]
    )
    SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093542', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Dan Bolan', N'Glenview', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093535', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bob Brennan', N'Redding', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007900', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Micheal Bubel', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007901', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Steve Burnett', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350547', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Justin Burrow', N'Yuba City', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007902', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bret Butcher', N'Seattle', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887619', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kim Van Houtte', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007904', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Quinn Carlsen', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33263570', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kathleen Carpenter', N'Chico', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703231', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jing Chen', N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007905', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Eric Chetwood', N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007907', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Coates', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350549', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Tyler Collier', N'Chico', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007908', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Paul Culbertson', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007909', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Blake Davelaar', N'Tucson', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007910', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Matt De Garmo', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093545', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Richard Del Monte', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007913', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Demko', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008232', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Darren Dindinger', N'Seattle', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007914', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michelle Disney', N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012075', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Alyse Dominguez', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007915', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Tad Doughty', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007916', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Glenn Downs', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007917', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kevin Duffy', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008227', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Scott Ebert', N'Denver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350554', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Dean Eisenbraun', N'Vancouver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093538', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Steve Eklund', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093544', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kent Erickson', N'Redding', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008228', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Patrick Fisk', N'Kennesaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G32497693', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Paige Foley', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008229', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Maria Foppiano', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35088455', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Corey Frank', N'Bel Air', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008230', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bob Frater', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093552', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Lisa Fulco', N'Bel Air', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008231', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Joshua Garcia', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012102', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Robert Gecker', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24733452', N'Primary', N'George McKelvey & Co. Primary', NULL, NULL, NULL, NULL, N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012103', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Chris Giordano', N'Los Gatos', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887616', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Rob Giunco', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012104', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Rutledge Gordon', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093548', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Gary Grewal', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703233', N'Advisor G Number (Secondary)', NULL, N'Allworth Guided Services', NULL, NULL, N'Gary Grewal', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G19378572', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Richard Gross', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35088461', N'Advisor G Number (Secondary)', NULL, N' ', NULL, NULL, N'Russ Hall', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093547', N'Advisor G Number (Secondary)', NULL, N'zz-Amy Wagner', NULL, NULL, N'Kyle Harvey', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093550', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jerry He', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012106', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Barbara Healy', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345954', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Lauren Heiman', N'Dansville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012107', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Eric Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012108', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Pat Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703229', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Matthew Holmes', N'Indianapolis NE', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012109', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'John Horseman', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093546', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Mike Hostetler', N'Kennesaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012110', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Steve Hruby', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G11562369', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kirk Hudson', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Non-Wrap', 0, N'G33806596', N'Primary', N'Indianapolis - Sheaff Brock (Non-Wrap)', N'SB Primary G Number', NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008410', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Laurie Ingwersen', N'Waltham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008409', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Roger Ingwersen', N'Waltham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012111', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Brian James', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008418', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'David Johanson', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703230', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kyle Kadish', N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008414', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Kane', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008419', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Matt Keller', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008420', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Adam Kint', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33263569', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'David Klaus', N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33263571', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Benjamin Knight', N'Chico', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008421', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Peter Knutson', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008411', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Gary Krasnov', N'Kennesaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008423', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Laurie Hadley', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012055', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Dexter Lamb', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012056', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Dan Leahy', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012057', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Scott Loochtan', N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887615', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Richard Looney', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012058', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bill Macher', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345955', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Brandon Mackie', N'Kennesaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35088458', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Patrick Maher', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012059', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Nicole Mayer', N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012061', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Austin McDaniel', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012062', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Judith McDaniel', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012063', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Evan McGrath', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093541', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Patrick McGrath', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012064', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Beau McGuire', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24873477', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Robert McKelvey', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887621', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Messinger', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012065', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'James Moore', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012066', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Stephanie Motzkus', N'Larkspur', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012067', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Terry Muchler', N'Dansville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012068', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Brian Murphy', N'Tucson', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012069', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jeremy Murray', N'Las Vegas', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012070', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Sean Murray', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012071', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Renee Nenninger', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G16198159', N'Advisor G Number (Secondary)', N'Norwood Team (Shorepoint)', NULL, NULL, NULL, NULL, N'Norwood', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012072', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Carol Novak', N'Bel Air', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012073', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Dan Novak', N'Bel Air', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012074', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Paul Ochel', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012099', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Adam Peters', N'Denver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012100', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Greg Phelps', N'Las Vegas', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34012101', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Hugh Phillips', N'Fairfield', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G38350558', N'Advisor G Number (Secondary)', N'Placeholder - do not use', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008234', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Deanna Purvis', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35088460', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Natalie Quirarte', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008415', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Fazley Rashid', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008233', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Sean Rayburn', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008236', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kelly Richards', N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008237', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Britton Riley', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35088457', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'James Risalvato', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008238', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'David Robertson', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008239', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Mark Rubey', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345953', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Rob Ryan', N'Yuba City', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350548', N'Advisor G Number (Secondary)', N'Indianapolis - Sheaff Brock (Wrap)', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345947', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Brent Sayler', N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G33263567', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Schankerman', N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008241', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'David Schauer', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345952', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Robby Scholes', N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008242', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Kat Schraeder', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008243', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bill Schretter', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703234', N'Advisor G Number (Secondary)', NULL, N'Allworth Guided Services', NULL, NULL, N'Bill Schretter', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093536', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Allison Scoggin', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093537', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Wesley Scoggin', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35088459', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'John Selzer', N'Glenview', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008240', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Andrew Shafer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350546', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Preet Shah', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345951', N'Advisor G Number (Secondary)', N'Sherman, Lori, Rob Gentry - Lafayette Branch', NULL, NULL, NULL, NULL, N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G19378573', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Mark Shone', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24729158', N'Advisor G Number (Secondary)', N'Sillicon Valley', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24729159', N'Advisor G Number (Secondary)', N'Sillicon Valley', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24729157', N'Advisor G Number (Secondary)', N'Sillicon Valley  - Main', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24729160', N'Advisor G Number (Secondary)', N'Sillicon Valley BrokerageLink', N' ', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350545', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Michael Slenes', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008245', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Ted Smalling', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008246', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Todd Smith', N'Kennesaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008247', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Eric Soetaert', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G24887622', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Daravy Son', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008403', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Bob Sponseller', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350550', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Carter Street', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008405', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Allegra Swan', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703235', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Logan Swallow', N'Indianapolis NE', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G35093543', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Lynda Tu', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38345949', N'Advisor G Number (Secondary)', N'Vancouver Office (CFG)', NULL, NULL, NULL, NULL, N'Vancouver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34007903', N'Advisor G Number (Secondary)', N'Visentin, Cali (nee Byrn)', NULL, NULL, NULL, N'Cali Visentin', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G38350551', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Brent Walker', N'Indianapolis NE', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008406', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Cheyenne Walker', N'Santa Rosa', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703232', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'David Weiss', N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008408', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Donella Winkler', N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G34008413', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jerod Yee', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34007906', NULL, N'ZZ-Christl, Matt', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G35088456', NULL, N'ZZ-Cleland, Brayden', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34007911', NULL, N'ZZ-DeBoer, Jeff', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34007912', NULL, N'ZZ-DeGreen, Sam', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34012105', NULL, N'ZZ-Grellas, Chris', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G35093551', NULL, N'ZZ-Harrison, Stratton', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008412', NULL, N'ZZ-Howard, Ron', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G32395723', NULL, N'ZZ-Kadish, Josh', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G33268919', NULL, N'ZZ-Knight, Diane ', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008422', NULL, N'ZZ-Kuniholm, Mark', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34012060', NULL, N'ZZ-Mayer, Richard', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008416', NULL, N'ZZ-Mazanec, Tim', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G35093540', NULL, N'ZZ-Modrak, Allison', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008235', NULL, N'ZZ-Rausch, Dan', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008244', NULL, N'ZZ-Scott, Alex', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G35093539', NULL, N'ZZ-Select Service - Stephanie Lewis', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008404', NULL, N'ZZ-Sprovach, Steve', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G34008407', NULL, N'ZZ-Williams, Lauren', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 0, N'G42703236', N'Advisor G Number (Secondary)', NULL, NULL, NULL, NULL, N'Jack Welty', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, N'Wrap', 0, N'G42703237', N'Advisor G Number (Secondary)', N'WRAP', N'Unassigned Advisor G Number', NULL, NULL, N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G38345950', N'Secondary', N'Private Client 102', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G38350553', N'Secondary', N'Private Client 103', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G38350552', N'Secondary', N'Private Client 117', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G38350557', N'Secondary', N'Private Client 119', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G38350556', N'Secondary', N'Private Client 124', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G38350555', N'Secondary', N'Private Client 128', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Wrap', 1, N'G42703238', N'Secondary', N'Private Client 130', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Non-Wrap', 0, N'G08638102', NULL, N'Shorepoint - Non-Wrap', NULL, NULL, NULL, NULL, N'Norwood', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15266380', NULL, N'HANSON MCCLAIN ADVISORS', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16198158', NULL, N'ALLWORTH FINANCIAL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G16198160', NULL, N'ALLWORTH FINANCIAL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G20703694', NULL, N'ALLWORTH FINANCIAL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20771569', NULL, N'ALLWORTH FINANCIAL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G24887620', NULL, N'GEORGE MCKELVEY & CO.', NULL, NULL, NULL, NULL, N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32460838', NULL, N'GEORGE MCKELVEY & CO.', NULL, NULL, NULL, NULL, N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G33292500', NULL, N'AWF-Shorepoint TPAM', NULL, NULL, NULL, NULL, N'Norwood', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G33690351', N'Secondary', N'Indianapolis - Sheaff Brock', N'SB Block Account G Number - mandatory for trading', NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G34361149', NULL, N'ALLWORTH FINANCIAL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 1, N'G34647311', N'Secondary', N'Private Client 109', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34647312', NULL, N'SHEAFF BROCK', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34647313', NULL, N'SHEAFF BROCK', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34647314', NULL, N'SHEAFF BROCK', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34647315', NULL, N'SHEAFF BROCK', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G35196032', NULL, N'SHEAFF BROCK', NULL, NULL, NULL, NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G41258015', NULL, N'Fiduciary Partners Trust Co - Data Imports', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G20689119', N'SAM Master', NULL, NULL, NULL, NULL, NULL, NULL, N'55I, LLC', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G27237352', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'55I, LLC', N'55ip Model Portfolios', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G19231610', N'SAM Master', NULL, NULL, NULL, NULL, NULL, NULL, N'SpiderRock Advisors, LLC', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G19231611', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'SpiderRock Advisors, LLC', N'Hedged Equity Concentrated Stock', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G19231612', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'SpiderRock Advisors, LLC', N'Hedged Equity Portfolio - Collar', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G19231620', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'SpiderRock Advisors, LLC', N'Managed Index Income', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G21409510', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'SpiderRock Advisors, LLC', N'Exchange Fund Replication', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G11455128', N'SAM Master', NULL, NULL, NULL, NULL, NULL, NULL, N'Aperio Group, LLC', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G13111454', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Aperio Group, LLC', N'Non-SRI Domestic', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G13257494', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Aperio Group, LLC', N'Socially Responsible', NULL, NULL, NULL, NULL;

    INSERT INTO tho.repcodes (
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts], [fidelity_g_number], [g_number_usage], [description], [notes], [schwab_master_account], [master_account_type], [allworth_advisor], [allworth_office], [separate_account_manager], [sma_strategy], [other_third_party], [american_funds_rep_number], [american_funds_branch_number], [bloomwell_529_rep_code]
    )
    SELECT N'Fidelity', 1, NULL, 0, N'G13667505', N'SAM Master', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G18008210', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', N'Corporate FI Ladder 1-5 Year', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G18008211', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', N'Corporate Ladder 1-10 Year', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G16444208', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', N'Municipal FI Ladder 1-5 Year', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G16444209', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', N'Municipal FI Ladder 1-10 Year', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G13869371', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', N'US Intermediate Taxable Fixed Income', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G13869375', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Blackrock Investment Management, LLC', N'Intermediate Municipal Fixed Income', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G13346883', N'SAM Master', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G30871673', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Tax -Smart U.S. Large Cap Leaders', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G30871672', N'Secondary', NULL, N'55ip overlay G number for taxable account JPM SMA strategies', NULL, NULL, NULL, NULL, N'55I, LLC', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G26847376', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Large Cap Leaders', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34196662', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Tax-Smart - U.S. All Cap Index Strategy (Russell 3000) ', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G30871674', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Tax-Smart - U.S. Large Cap Index Strategy (S&P 500)', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G41389480', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Tax-Smart - U.S. Large-Mid Cap Growth Index Strategy (Russell 1000 Growth)', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G41389481', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Tax-Smart - U.S. Large-Mid Cap Value Index Strategy (Russell 1000 Value)', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37673207', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'JPMorgan', N'Tax-Smart - International Developed ADR Index Strategy (MSCI EAFE ADR)', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, N'Non-Wrap', 0, N'G40700104', N'Primary', N'AQR  - LSMA Primary  - SMA', N'AQR SMA - Must be in the Primary (Top) Spot for correct pricing - Level 5 Options needed', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G31244508', N'SAM Master', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32231487', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Integrated Flex 145 R3', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32224597', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Integrated Flex 145 R1', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34638239', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Integrated Flex 200 R3', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G34638240', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Integrated Flex 200 R1', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37479423', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Concentrated Stock Flex 200 R3', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37476746', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Concentrated Stock Flex 200 R1', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G33429489', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Integrated Flex 250 R3', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G33429488', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Integrated Flex 250 R1', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37476745', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Concentrated Stock Flex 250 R3', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37476744', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'AQR Capital Management, LLC', N'Concentrated Stock Flex 250 R1', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G10528860', N'SAM Master', N'Envestnet', N'Only for Envestnet SMA/UMA Platform, SMA applications', NULL, NULL, NULL, NULL, N'Envestnet Advisory Corp', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G12864151', N'Product', NULL, NULL, NULL, NULL, NULL, NULL, N'Envestnet Asset Management Inc.', N'Envestnet UMA', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11591839', N'SAM Master', N'Legacy SMA', NULL, NULL, NULL, NULL, NULL, N'Abner Herrman & Brock', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11591843', N'Product', N'Legacy SMA', NULL, NULL, NULL, NULL, NULL, N'Abner Herrman & Brock', N'Large Cap Core', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G11591845', N'Product', N'Legacy SMA', NULL, NULL, NULL, NULL, NULL, N'Abner Herrman & Brock', N'Taxable Custom Balanced', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15845058', N'SAM Master', N'Legacy SMA', NULL, NULL, NULL, NULL, NULL, N'Capital Group', NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G23478163', N'Product', N'Legacy SMA', N'Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Core', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G23499277', N'Product', N'Legacy SMA', N'Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Growth', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G23499278', N'Product', N'Legacy SMA', N'Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Income and Growth', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20672263', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Equity', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G30860193', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Flexible Growth', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G30864585', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Flexible Growth & Income', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G30864586', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'US Conservative Growth & Income', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15833746', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'Global Equity', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G23499279', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'Global Growth', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15833744', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'World Dividend Growers', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G15833745', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'International Equity', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G23499280', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'International Growth', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20672265', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'Short Muni', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20672261', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'Intermediate Muni', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20672262', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'Long Muni', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G20672264', N'Product', N'Legacy SMA', N'Not Approved', NULL, NULL, NULL, NULL, N'Capital Group', N'Core Bond', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Allworth Master', N'FA Master, WRAP', N'0807-5229', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Allworth Financial (Non-Wrap)', N'COURTESY & SCHWAB CHARITABLE', N'0823-2168', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Allworth PCRA (NON TPFG)', N'TBP non-wrap', N'0844-7382', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Allworth Financial (Non-Trading, Wrap)', N'TBP WRAP', N'0872-0401', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Allworth Non-discretionary PCRA', N'For non-dsicretionary PCRA accounts', N'0846-2245', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Albuquerque Branch FA Master', N'WRAP, Orion Dual feeds', N'0846-2039', N'FA', NULL, N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Phoenix Courtesy Accts FA Master', NULL, N'0833-9776', N'FA', NULL, N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Durham Office FA Master', N'WRAP, Orion Dual feeds', N'0803-7596', N'FA', NULL, N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Mark Shone FA Master', N'WRAP, For Dual feeds', N'0822-4692', N'FA', N'Mark Shone', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'RAA Non-Wrap FA Master', NULL, N'0811-9689', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'RAAs Non-Wrap FA Master', N'No Wrap agreement, TBP', N'0811-9711', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Howard / Demko Office Non-Wrap FA Master', NULL, N'0844-0533', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Stewart & Patten, Lafayette Office FA WRAP Master', NULL, N'0825-4339', N'FA', NULL, N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Stewart & Patten, Lafayette Office FA Non-Wrap Master', NULL, N'0800-0108', N'FA', NULL, N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Stewart & Patten, Lafayette FA - PCRA Non-Wrap Master', N'PCRA, Non-Wrap', N'0819-0909', N'FA', NULL, N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Roseville Galleria FA Master', NULL, N'0871-3069', N'FA', NULL, N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'San Jose (formally SVW) ', N'Scott Ponder, Scott Yang, Tracy Lasecke', N'0813-3640', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'San Jose (formally SVW) ', NULL, N'0800-6518', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Walnut Creek - DMG', N'Non Wrap (Charitable) / Schwab 529s FA Master', N'0800-9624', N'FA', NULL, N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Waltham Office FA Master', NULL, N'0844-1232', N'FA', NULL, N'Waltham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'Waltham Courtesy Accts FA Master', NULL, N'0818-7356', N'FA', NULL, N'Waltham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Yuba City - TEAM MASTER', NULL, N'0878-2619', N'FA', NULL, N'Yuba City', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Riverwoods Office SL Master', N'SL (Secondary master) For Orion imports', N'0807-0183', N'SL', NULL, N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Albuquerque Office SL Master', N'SL (Secondary master) For Orion imports', N'0839-0222', N'SL', NULL, N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Durham Office SL Master', N'SL (Secondary master) For Orion imports', N'0870-3928', N'SL', NULL, N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Vegas Office SL Master', N'SL (Secondary master) For Orion imports', N'0846-8989', N'SL', NULL, N'Las Vegas', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'San Jose Office SL Master', N'SL (Secondary master) For Orion imports', N'0842-1498', N'SL', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'San Jose Office HYIC SL Master', N'SL (Secondary master) For Investor Checking', N'0803-7136', N'SL', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Walnut Creek - DMG SL Master', N'SL (Secondary master) For Black Diamond imports', N'0849-3213', N'SL', NULL, N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Lawrence Office SL Master', N'SL (Secondary master) For Orion imports', N'0833-5300', N'SL', NULL, N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Closed Accounts', N'Non-Trading Master (DOES NOT FEED TO TAMARAC)', N'0821-0662', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'AWF HYIC SL Master', NULL, N'0813-1925', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'CRP - SAN SL Master', NULL, N'0830-0046', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'AWF Non-Trading Master', N'Non-Trading Master (Feeds to Tamarac)', N'0848-7055', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Deceased Account Master', NULL, N'0821-2862', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Schwab Annuity Master', NULL, N'0834-8618', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Schwab 529s FA Master', N'Shared with multi Advisors', N'0846-8389', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'San Jose (SVW) - Schwab 529s FA Master', NULL, N'0800-0092', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Schwab Banking - PAAL Accounts & HYIC', NULL, N'0847-3333', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'55ip Download SL Master (0813-4587 for viewing)', NULL, N'0832-1153', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Tamarac Download SL Master', NULL, N'0817-3658', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'TPFG - PCRA ( & 0825-4134)', N'Need both Masters on paperwork', N'0821-2037', N'FA', NULL, NULL, NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Journey - GoldRiver Branch', NULL, N'0800-9038', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0801-4419', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0801-8501', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0804-3525', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Remove from Orion Imports', N'No accounts linked', N'0804-4656', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Remove from Orion Imports', N'No accounts linked', N'0805-3149', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0805-5102', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Journey - Temple Branch', NULL, N'0806-5508', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0806-7815', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'UAS - OLD', N'No accounts linked', N'0812-6183', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'RAAs', N'15 accounts - all $0', N'0813-9883', N'SL', NULL, N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0815-8868', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0816-5539', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'RG Capital (deceased client)', NULL, N'0816-9761', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Adam Chetwood - OLD Non-managed Master', NULL, N'0817-1334', N'FA', NULL, N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'UAS - OLD Master', NULL, N'0817-3018', N'FA', NULL, N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Morningstar ByAll?', N'No accounts linked', N'0818-7385', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'RAAs', N'12 accounts - all $0', N'0821-5303', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0821-8047', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0822-4763', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Adam Chetwood OLD MASTER - DO NOT USE', N'1 account linked with no balance', N'0823-0832', N'FA', NULL, N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Allworth Financial', NULL, N'0824-8939', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, NULL, N'0825-8209', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0826-0593', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'RAAs', N'14 accounts linked with no balances', N'0828-5492', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0828-6720', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'DO NOT USE Allworth PCRA Master (TBP non-wrap)-pending', N'No accounts linked', N'0829-1541', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Original Allworth master - DO NOT USE', NULL, N'0829-5108', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'Mark Shone Wealth Management', N'Acquired - no new accounts', N'0829-9646', N'FA', N'Mark Shone', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Allworth Financial', NULL, N'0830-6193', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0832-6579', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0832-8769', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Adam Chetwood - OLD Nondiscretionary Master', N'No accounts linked', N'0833-2117', N'FA', NULL, N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Allworth Financial', NULL, N'0834-1134', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Allworth Financial', NULL, N'0835-1685', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0836-4955', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Allworth Financial', N'1 account linked', N'0837-2262', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0838-0569', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Data Sources (Albridge Solutions)', N'No accounts linked', N'0839-3442', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'RAAs PCRA (ABP non-wrap) - DO NOT USE', N'ABP non-wrap - OLD PCRA - no New Accounts) - 121 Accounts linked', N'0840-8638', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0843-3155', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0843-5791', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0844-8215', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'DeGreen (?)', N'No accounts linked', N'0844-8602', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0845-4620', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, NULL, N'No accounts linked', N'0846-0882', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'Allworth Financial', N'Data Sources (Albridge Solutions)', N'0846-4065', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-8238', N'FA', N'Adam Kint', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0829-7696', N'FA', N'Adam Peters', N'Denver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0827-7806', N'FA', N'Allegra Swan', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, NULL, N'0866-7058', N'FA', N'Chuck Alexander', N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0845-1333', N'FA', N'Alyse Dominguez', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0848-8462', N'FA', N'Amy Bertle', N'Denver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0839-4697', N'FA', N'Andrew Shafer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0849-8795', N'FA', N'Andrew Shafer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0814-5621', N'FA', N'Austin McDaniel', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0827-8925', N'FA', N'Barbara Healy', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0803-7865', N'FA', N'Beau McGuire', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0866-8447', N'FA', N'Benjamin Abraham', N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0898-7549', N'FA', N'Benjamin Knight', N'Chico', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0841-2181', N'FA', N'Bill Schretter', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0845-7892', N'FA', N'Bill Schretter', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Allworth Guided Services', N'Schretter, Bill (AGS)', N'0813-9010', N'FA', N'Bill Schretter', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0807-7986', N'FA', N'Blake Davelaar', N'Tucson', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0801-6866', N'FA', N'Bob Benyamin', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0894-0670', N'FA', N'Bob Brennan', N'Redding', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0826-0838', N'FA', N'Bob Frater', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0822-2049', N'FA', N'Bob Sponseller', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0825-1493', N'FA', N'Bob Sponseller', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, NULL, N'0811-1481', N'FA', N'Brandon Mackie', N'Kennesaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0881-6329', N'FA', N'Brent Sayler', N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0816-6722', N'FA', N'Bret Butcher', N'Seattle', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0841-2408', N'FA', N'Brian James', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0843-0777', N'FA', N'Brian James', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0838-8503', N'FA', N'Brian Murphy', N'Tucson', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0819-4201', N'FA', N'Britton Riley', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0830-4952', N'FA', N'Britton Riley', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0817-2954', N'FA', N'Cali Visentin', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, N'Wrap', N'0885-9615', N'FA', N'Carter Street', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0807-2739', N'FA', N'Cheyenne Walker', N'Santa Rosa', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'GW&K Investment Management', N'0802-9648', N'FA', N'Chris Giordano', N'Los Gatos', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Legacy SMA', N'Parametric Associates Equity', N'0806-3194', N'Managed Account FA', N'Chris Giordano', N'Los Gatos', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Legacy SMA', N'RNC Genter', N'0813-3378', N'Managed Account FA', N'Chris Giordano', N'Los Gatos', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Legacy SMA', N'Abner Herrman & Brock', N'0818-5994', N'Managed Account FA', N'Chris Giordano', N'Los Gatos', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'AW new accounts', N'0827-3614', N'FA', N'Chris Giordano', N'Los Gatos', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0801-9580', N'FA', N'Corey Frank', N'Bel Air', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0876-4654', N'FA', N'Dan Bolan', N'Glenview', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0857-4526', N'FA', N'Dan Leahy', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-8825', N'FA', N'Dan Rausch', N'Grandville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0879-2290', N'FA', N'Danny Valenzuela ', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0839-8098', N'FA', N'Darren Dindinger', N'Seattle', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0819-7052', N'FA', N'David Bastoni', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0810-7518', N'FA', N'David Klaus', N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0815-2682', N'FA', N'David Johanson', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0834-0080', N'FA', N'David Schauer', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0803-8766', N'FA', N'Davis Blomquist', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0824-9884', N'FA', N'Deanna Purvis', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0832-8649', N'FA', N'Deanna Purvis', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0803-5584', N'FA', N'Dexter Lamb', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0810-0168', N'FA', N'Eric Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0843-8849', N'FA', N'Eric Soetaert', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0840-7491', N'FA', N'Evan McGrath', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0891-2204', N'FA', N'Fazley Rashid', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Freemon Corp Trustee Only (C.Giordano)', N'0847-6234', N'FA', NULL, NULL, NULL, NULL, N'Fremont Bank / Sungard', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0827-6046', N'FA', N'Gary Grewal', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0816-5353', N'FA', N'Gary Grewal', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Allworth Guided Services', N'Grewal, Gary (AGS)', N'0899-6134', N'FA', N'Gary Grewal', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0812-7718', N'FA', N'Laurie Hadley', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL;

    INSERT INTO tho.repcodes (
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts], [fidelity_g_number], [g_number_usage], [description], [notes], [schwab_master_account], [master_account_type], [allworth_advisor], [allworth_office], [separate_account_manager], [sma_strategy], [other_third_party], [american_funds_rep_number], [american_funds_branch_number], [bloomwell_529_rep_code]
    )
    SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0810-4229', N'FA', N'Glenn Downs', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0825-1487', N'FA', N'Glenn Downs', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0832-7668', N'FA', N'Greg Phelps', N'Las Vegas', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0832-8910', N'FA', N'Hugh Phillips', N'Fairfield', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, N'Indianapolis - Sheaff Brock', NULL, N'0848-7694', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Indianapolis NE Team (Brent Walker, Matthew Holmes)', NULL, N'0857-0715', N'FA', NULL, N'Indianapolis NE', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0830-0097', N'FA', N'Ted Smalling', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-0687', N'FA', N'James Moore', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0897-3635', N'FA', N'James Risalvato', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0836-5512', N'FA', N'Jeremy Murray', N'Las Vegas', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0803-1612', N'FA', N'Jerod Yee', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0875-6707', N'FA', N'Jerry He', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0814-4619', N'FA', N'Jing Chen', N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0837-2727', N'FA', N'John Horseman', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0883-2346', N'FA', N'John Selzer', N'Glenview', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0800-7832', N'FA', N'Joshua Garcia', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0806-5962', N'FA', N'Judith McDaniel', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'For Dual feeds (eMoney)', N'0818-8126', N'FA', N'Kelly Richards', N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, NULL, N'0818-2686', N'FA', N'Kathleen Carpenter', N'Chico', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0890-5909', N'FA', N'Kent Erickson', N'Redding', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0805-5244', N'FA', N'Kevin Duffy', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0833-8952', N'FA', N'Kevin Duffy', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0822-3465', N'FA', N'Kirk Hudson', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0833-3899', N'FA', N'Leonardo Borjorquez', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0808-0417', N'FA', N'Kyle Harvey', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0878-0919', N'FA', N'Kyle Harvey', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, NULL, N'0835-1316', N'FA', N'Kyle Kadish', N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0808-7783', N'FA', N'Lauren Heiman', N'Dansville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'AW new accounts', N'0896-1686', N'FA', N'Lisa Fulco', N'Bel Air', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0855-0619', N'FA', N'Lynda Tu', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Manasquan - TEAM Master', N'Core Satelite, Active Plus, Pure Index', N'0845-1922', N'FA', NULL, N'Manasquan', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0892-2888', N'FA', N'Maria Foppiano', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0804-7855', N'FA', N'Mark Rubey', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0801-1538', N'FA', N'Mark Shone', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0813-0428', N'FA', N'Matt De Garmo', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-1475', N'FA', N'Matt Keller', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0848-3225', N'FA', N'Michael Bubel', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0825-2939', N'FA', N'Michael Coates', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-7769', N'FA', N'Michael Coates', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'AW new accounts', N'0822-8174', N'FA', N'Michael Demko', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0827-7291', N'FA', N'Michael Hostetler', N'Kenessaw', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0820-6506', N'FA', N'Michael Schankerman', N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-1869', N'FA', N'Michael Slenes', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'AW new accounts', N'0845-6252', N'FA', N'Natalie Quirarte', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0836-3321', N'FA', N'Nicole Mayer', N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0814-4390', N'FA', N'Pat Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0819-0436', N'FA', N'Pat Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0811-6672', N'FA', N'Pat McClain', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0821-1429', N'FA', N'Pat McClain', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0811-2019', N'FA', N'Patrick McGrath', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0822-6448', N'FA', N'Paul Culbertson', N'Houston', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0864-3054', N'FA', N'Paul Ochel', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0822-2157', N'FA', N'Peter Abi-Nader', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0817-1522', N'FA', N'Peter Knutson', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, NULL, N'0897-1941', N'FA', N'Preet Shah', N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0824-4479', N'FA', N'Quinn Carlsen', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0805-3308', N'FA', N'Renee Nenninger', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, NULL, N'AW new accounts (Walnut Creek - DMG)', N'0862-9644', N'FA', N'Richard Del Monte', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0829-3010', N'FA', N'Richard Gross', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0815-8713', N'FA', N'Robert Gecker', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0837-7628', N'FA', N'Robert Scholes', N'Durham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'AW Retirement Plan Services', N'Core Satelite, Active Plus, Pure Index', N'0839-7515', N'FA', NULL, N'RPS', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'AW new accounts', N'0829-8914', N'FA', N'Russ Hall', N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0846-8126', N'FA', N'Scott Ebert', N'Denver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0832-5890', N'FA', N'Scott Hanson', N'Folsom', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0831-7352', N'FA', N'Scott Loochtan', N'Riverwoods', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0822-3656', N'FA', N'Sean Murray', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0803-5023', N'FA', N'Sean Rayburn', N'Addison', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0830-4774', N'FA', N'Stephanie Bemerer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0844-7847', N'FA', N'Stephanie Bemerer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0830-4720', N'FA', N'Stephanie Motzkus', N'Larkspur', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0826-1060', N'FA', N'Steve Burnett', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0834-1841', N'FA', N'Steve Burnett', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0802-6053', N'FA', N'Steve Hruby', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Dynamic models', N'0818-6878', N'FA', N'Steve Hruby', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0821-9418', N'FA', N'Tad Doughty', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0834-5632', N'FA', N'Terry Muchler', N'Dansville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0848-6563', N'FA', N'Tyler Collier', N'Chico', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Vancouver TEAM Master', NULL, N'0851-8754', N'FA', NULL, N'Vancouver', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Orion Dual Feeds | Core Satelite, Active Plus, Pure Index', N'0822-3691', N'FA', N'Victoria Bogner', N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0844-0269', N'FA', N'Wesley Scoggin', N'Roseville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Core Satelite, Active Plus, Pure Index', N'0802-7317', N'FA', N'Bill Macher', N'St Louis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAllison Modrak', N'Core Satelite, Active Plus, Pure Index', N'0825-2202', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAlex Scott', N'Dynamic models', N'0803-4697', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAlex Scott', N'Core Satelite, Active Plus, Pure Index', N'0837-8210', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzCarol Novak', N'Core Satelite, Active Plus, Pure Index', N'0837-4839', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzChris Brown', N'Core Satelite, Active Plus, Pure Index', N'0828-6111', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzChristopher Grellas', N'Core Satelite, Active Plus, Pure Index', N'0849-7399', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzDan Novak', N'Core Satelite, Active Plus, Pure Index', N'0803-9905', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzJeff DeBoer', N'Core Satelite, Active Plus, Pure Index', N'0821-5665', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzLauren Williams', N'Core Satelite, Active Plus, Pure Index', N'0845-5122', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzMatthew Christl', N'Core Satelite, Active Plus, Pure Index', N'0846-2680', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzRichard Mayer', N'Core Satelite, Active Plus, Pure Index', N'0826-4982', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzRichard Mayer', N'Dynamic models', N'0826-6817', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzRon Howard', N'AW new accounts', N'0838-2662', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzStephanie Lewis', N'Core Satelite, Active Plus, Pure Index', N'0839-6831', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzSteve Sprovach', N'Core Satelite, Active Plus, Pure Index', N'0812-6783', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzSteve Sprovach', N'Dynamic models', N'0836-1048', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0809-7009', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0843-3502', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0824-7974', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0895-6571', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0863-6072', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0832-2477', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0844-0874', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0838-0155', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0856-1315', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0850-2867', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0851-8927', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0876-8366', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, NULL, N'Unassigned Advisor FA Master', N'0883-1339', N'FA', N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Schwab - Private Client', N'Wrap - Main FA Private/Restricted Master | Need to add SLs to link Advisor', N'0869-1871', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Schwab - Private Client PCRA', N'Non-Wrap FA Master | Need to add SLs to link Advisor', N'0886-7581', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 55ip Marketplace Master', N'Wrap - Marketplace Master Sect 2:  55I, LLC: 0816-6348 | Need to add SLs to link Advisor', N'0846-5407', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client CIBC Marketplace', N'Wrap - Marketplace Master | Need to add SLs to link Advisor', N'0891-1897', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client Marketplace Master', N'Wrap - Marketplace Master  - use with any SMA not 55ip | Need to add SLs to link Advisor', N'0808-0133', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 101', NULL, N'0862-3138', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 102', NULL, N'0890-1086', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 103', NULL, N'0819-1632', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 105, Private Client 127', NULL, N'0811-1260', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 106', NULL, N'0890-6769', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 107', NULL, N'0802-6153', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 1, NULL, NULL, N'Private Client 108', NULL, N'0883-8195', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 109', NULL, N'0840-4554', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 110', NULL, N'0820-3466', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 111', NULL, N'0831-9946', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 112', NULL, N'0817-6863', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 113', NULL, N'0809-0463', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 114', NULL, N'0801-7238', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 115', NULL, N'0836-3497', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 115', NULL, N'0812-6562', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 116', NULL, N'0807-0962', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 1, NULL, NULL, N'Private Client 116', NULL, N'0821-5235', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 1, NULL, NULL, N'Private Client 118', NULL, N'0879-0126', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 1, NULL, NULL, N'Private Client 120 ', NULL, N'0810-6114', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 1, NULL, NULL, N'Private Client 121', NULL, N'0852-5660', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 1, NULL, NULL, N'Private Client 123', NULL, N'0864-9287', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 1, NULL, NULL, N'Private Client 130', NULL, N'0867-2081', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 1, NULL, NULL, N'Unassigned - SL (Private Client)', NULL, N'0809-9244', N'SL', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - IP', N'Allworth Innovative Portfolios', N'0818-4483', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'FSA Non-Wrap', NULL, N'0805-5958', N'FA', NULL, N'Needham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Indianapolis - Sheaff Brock', NULL, N'0841-5884', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'SB - in SSB strat Non-Wrap', N'Salzinger Sheaff Brock', N'0811-5061', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - Individual Portfolio Management', NULL, N'0838-2568', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzLafayette', N'Stewart & Patten', N'0827-6197', N'FA', NULL, N'Lafayette', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzMuchler Managed Account Master', N'Used for 1 Blackrock SMA', N'0820-9258', N'Managed Account FA', N'Terry Muchler', N'Dansville', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzLawrence', N'1 account linked, advisor Eric Soetaert', N'0846-0311', N'FA', NULL, N'Lawrence', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'AW - Norwood Non-Wrap FA Master', NULL, N'0806-4658', N'FA', NULL, N'Norwood', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Indianapolis - Salzinger Sheaff Brock', NULL, N'0810-4617', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - Non-IP Pfd', NULL, N'0832-7010', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'zzSVW Nonwrap Mkt - do not use', N'Silicon Valley SpiderRock, 2 accounts linked', N'0836-2385', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzEric Henry', N'11 accounts Eric Henry, 1 account Allegra Swan', N'0838-7225', N'FA', N'Eric Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzPat Henry', N'1 account linked', N'0827-8362', N'FA', N'Pat Henry', N'Sacramento', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAllworth Managed Account Master', N'Appears to have been used for Aperio, 10 accounts linked', N'0827-9547', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - Oppenheimer', NULL, N'0806-3727', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzMark Shone', N'1 account linked', N'0807-3098', N'FA', N'Mark Shone', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'AW - Denton Non-Wrap FA Master', N'Grunden', N'0814-2763', N'FA', NULL, N'Denton', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - Jim BUP', NULL, N'0816-2017', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - SSB Closed', NULL, N'0896-1177', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SM - Courtesy Legacy', N'Simply Money', N'0825-9296', N'FA', NULL, N'Cincinnati', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzHall Private Wealth Advisors', N'Mostly Russ Hall accounts, some Patrick McGrath and Natalie Quirarte', N'0829-1121', N'FA', NULL, N'San Diego', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzSilicon Valley', N'6 accounts linked', N'0823-0560', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzUnknown Allworth FA Master', N'2 accounts with no balance linked', N'0897-0480', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzSVW Donor Advised Fund', N'1 account linked', N'0830-9602', N'FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAW - 55ip Marketplace (TD-bill direct)', N'25 accounts linked', N'0828-8882', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzDel Monte', N'1 account with no balance linked', N'0827-1516', N'FA', N'Richard Del Monte', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'zzWPA - Non-Wrap Master', N'4 acocunts with no balance linked', N'0839-3514', N'FA', NULL, N'Indianapolis NE', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'AW - Salzinger, Mark Nonwrap', NULL, N'0801-0016', N'FA', N'Mark Salzinger', N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - Closed', NULL, N'0892-0952', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAW - 55ip Marketplace - TD HNW', NULL, N'0815-6223', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Non-Wrap', 0, NULL, NULL, N'zzAW - Richards, Kelly (Non-Wrap)', NULL, N'0846-7455', N'FA', N'Kelly Richards', N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzHarvest Group', NULL, N'0812-4120', N'FA', NULL, N'Waltham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzSVW - Marketplace FA', N'1 SpiderRock account linked', N'0808-2678', N'Managed Account FA', NULL, N'Campbell', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 1, NULL, NULL, N'zzJim McMahon', N'1 account linked', N'0811-6294', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzUnknown Allworth FA Master', N'1 closed account linked', N'0818-8546', N'FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'SB - SBIA Courtesy', NULL, N'0838-2060', N'FA', NULL, N'Indianapolis SB', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, NULL, 0, NULL, NULL, N'zzAW - Marketplace Blackrock TDA', N'1 closed account linked', N'0801-9543', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Non-Wrap', 0, NULL, NULL, N'AQR Marketplace Master', N'Non-Wrap,  AQR’s BT Master: 0844-8803', N'0838-0301', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0844-8803', N'Manager BT', NULL, NULL, N'AQR Capital Management, LLC', N'AQR Flex SMAs - Lower and Higher Leverage', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'55ip Marketplace Master', N'WRAP, Sect 2:  55I, LLC: 0816-6348', N'0822-6814', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0816-6348', N'Manager BT', NULL, NULL, N'55I, LLC', N'55ip Model Portfolios', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Aperio/BlackRock/JP Morgan SMA Marketplace', NULL, N'0801-4369', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0835-7611', N'Manager BT', NULL, NULL, N'Aperio Group, LLC', N'Aperio Non-SRI Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0806-0554', N'Manager BT', NULL, NULL, N'Aperio Group, LLC', N'Aperio SRI Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0823-4515', N'Manager BT', NULL, NULL, N'Blackrock Investment Management, LLC', N'Bond Ladder and Fixed Income Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Used for Tax-Smart - U.S. Large-Cap Leaders and Tax-Smart - Int''l Developed ADR Index', N'0810-9619', N'Manager BT', NULL, NULL, N'JPMorgan', N'Active & International Index Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0852-7597', N'Manager BT', NULL, NULL, N'JPMorgan', N'JP Morgan US Large-Cap Leaders', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, N'Used for multiple JPM direct index strategies', N'0836-5037', N'Manager BT', NULL, NULL, N'JPMorgan', N'Domestic Index Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Envestnet UMA/ TAMP', NULL, N'0880-7779', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0825-0983', N'Manager BT', NULL, NULL, N'Envestnet Asset Management Inc.', N'Envestnet Unified Managed Account', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, N'Phoenix Marketplace ', NULL, N'0833-0600', N'Managed Account FA', NULL, N'Phoenix', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Legacy SMA - CIBC Marketplace Master', N'WRAP - Indianapolis office', N'0841-5228', N'Managed Account FA', NULL, N'Indianapolis', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, N'Waltham Marketplace Master', NULL, N'0834-1340', N'Managed Account FA', NULL, N'Waltham', NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'Legacy SMA Marketplace Master', NULL, N'0813-7775', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, N'Wrap', 0, NULL, NULL, N'AW Marketplace - Spiderrock & Capital Group', N'WRAP -  Capital Group BT Master 0848-2494', N'0828-7298', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0840-8928', N'Manager BT', NULL, NULL, N'SpiderRock Advisors, LLC', N'Multiple SpiderRock Options Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, NULL, NULL, N'0848-2494', N'Manager BT', NULL, NULL, N'Capital Group', N'Multiple Capital Group Strategies', NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 0, N'Wrap', 0, NULL, NULL, N'San Jose (formally SVW)- Marketplace ', NULL, N'0838-5307', N'Managed Account FA', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37309406', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Benjamin Abraham', N'Indianapolis', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G15845072', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'David Bastoni', N'Folsom', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL;

    INSERT INTO tho.repcodes (
        [custodian], [actively_used], [wrap_fee_type], [for_employee_accounts], [fidelity_g_number], [g_number_usage], [description], [notes], [schwab_master_account], [master_account_type], [allworth_advisor], [allworth_office], [separate_account_manager], [sma_strategy], [other_third_party], [american_funds_rep_number], [american_funds_branch_number], [bloomwell_529_rep_code]
    )
    SELECT N'Fidelity', 1, NULL, 0, N'G30481341', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Bob Benyamin', N'Roseville', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37916641', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Amy Bertle', N'Denver', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778808', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Davis Blomquist', N'Folsom', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G39192554', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Leonardo Bojorquez', N'Walnut Creek', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778814', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Bret Butcher', N'Seattle', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32740571', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Quinn Carlsen', N'Sacramento', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778813', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Michael Coates', N'Cincinnati', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G36204763', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Matt De Garmo', N'Walnut Creek', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32422906', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Tad Doughty', N'Sacramento', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G40514240', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Kent Erickson', N'Redding', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778810', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Maria Foppiano', N'Folsom', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G39192790', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Gary Grewal', N'Sacramento', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G38453194', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Jerry He', N'Campbell', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37916631', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'David Klaus', N'Indianapolis', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G35208722', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Benjamin Knight', N'Chico', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778811', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Laurie Hadley', N'Roseville', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G38453206', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Nicole Mayer', N'Riverwoods', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32527408', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Beau McGuire', N'Sacramento', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32422905', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Stephanie Motzkus', N'Larkspur', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G31387894', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Hugh Phillips', N'Fairfield', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778812', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Britton Riley', N'Cincinnati', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778815', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Allison Scoggin', N'Roseville', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G32740579', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Ted Smalling', N'Sacramento', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37916630', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Bob Sponseller', N'Cincinnati', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G31387899', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Allegra Swan', N'Campbell', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37916634', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Lynda Tu', N'Campbell', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G29060689', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Cheyenne Walker', N'Santa Rosa', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 1, NULL, 0, N'G37778809', N'Secondary', N'Advisor TPFG G Number', NULL, NULL, NULL, N'Jerod Yee', N'Folsom', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G37916638', NULL, N'ZZModrak, Allison', NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G33263558', NULL, N'ZZDeBoer, Jeff', NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G32422904', NULL, N'ZZGrellas, Chris', NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Fidelity', 0, NULL, 0, N'G28993213', NULL, N'ZZAndrew Kessler', NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0881-5743', N'SL', N'Benjamin Abraham', N'Indianapolis', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0886-4641', N'SL', N'Amy Bertle', N'Denver', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0848-3788', N'SL', N'Bret Butcher', N'Seattle', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0806-4083', N'SL', N'Tad Doughty', N'Sacramento', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0870-1808', N'SL', N'Jerry He', N'Campbell', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0871-9612', N'SL', N'Laurie Ingwersen', N'Waltham', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0815-4931', N'SL', N'David Klaus', N'Indianapolis', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0836-5152', N'SL', N'Bill Schretter', N'Cincinnati', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'Schwab', 1, NULL, 0, NULL, NULL, N'Advisor TPFG SL Master', NULL, N'0851-0965', N'SL', N'Jerod Yee', N'Folsom', NULL, NULL, N'The Pacific Financial Group', NULL, NULL, NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Adam Peters', N'Denver', NULL, NULL, NULL, N'462062', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, N'zzAndrew Kessler', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'473662', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 0, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Barbara Healy', N'Roseville', NULL, NULL, NULL, N'465606', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Beau McGuire', N'Sacramento', NULL, NULL, NULL, N'517884', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Benjamin Abraham', N'Indianapolis', NULL, NULL, NULL, N'40143391', N'637278', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Benjamin Knight', N'Chico', NULL, NULL, NULL, N'40025674', N'633523', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Blake Davelaar', N'Tucson', NULL, NULL, NULL, N'459947', N'555052', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Cheyenne Walker', N'Santa Rosa', NULL, NULL, NULL, N'449792', N'546779', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 0, NULL, 0, NULL, NULL, N'zzChristopher Brown', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'485067', N'553400', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Dan Novak', N'Bel Air', NULL, NULL, NULL, N'448865', N'617638', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'David Bastoni', N'Folsom', NULL, NULL, NULL, N'579812', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'David Klaus', N'Indianapolis', NULL, NULL, NULL, N'40026425', N'637278', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'David Schauer', N'Sacramento', NULL, NULL, NULL, N'425657', N'505966', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'David Schauer', N'Sacramento', NULL, NULL, NULL, N'425657', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Dexter Lamb', N'St Louis', NULL, NULL, NULL, N'589110', N'619680', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Diane Knight', N'Chico', NULL, NULL, NULL, N'40025675', N'633523', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Tad Doughty', N'Sacramento', NULL, NULL, NULL, N'480441', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Hugh Phillips', N'Fairfield', NULL, NULL, NULL, N'460041', N'546779', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Eric Chetwood', N'Durham', NULL, NULL, NULL, N'448038', N'545718', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Eric Chetwood', N'Durham', NULL, NULL, NULL, N'448038', N'625835', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Ted Smalling', N'Sacramento', NULL, NULL, NULL, N'441510', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'John Horseman', N'St Louis', NULL, NULL, NULL, N'594360', N'619680', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Joshua Garcia', N'Addison', NULL, NULL, NULL, N'40009751', N'554680', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Joshua Garcia', N'Addison', NULL, NULL, NULL, N'40009751', N'630744', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 0, NULL, 0, NULL, NULL, N'zzJoshua Kadish', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'40017623', N'628987', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Kathleen Carpenter', N'Chico', NULL, NULL, NULL, N'40025676', N'633523', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Laurie Hadley', N'Roseville', NULL, NULL, NULL, N'442431', N'505966', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Michael Schankerman', N'Indianapolis', NULL, NULL, NULL, N'40026424', N'637278', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Nicole Mayer', N'Riverwoods', NULL, NULL, NULL, N'40017624', N'628987', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Pat Henry', N'Sacramento', NULL, NULL, NULL, N'435704', N'505966', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Pat Henry', N'Sacramento', NULL, NULL, NULL, N'435704', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Paul Culbertson', N'Houston', NULL, NULL, NULL, N'554422', N'553400', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Peter Knutson', N'Lawrence', NULL, NULL, NULL, N'416501', N'650347', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Bob Frater', N'Houston', NULL, NULL, NULL, N'447393', N'553400', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Scott Loochtan', N'Riverwoods', NULL, NULL, NULL, N'40017625', N'628987', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'David Johanson', N'Campbell', NULL, NULL, NULL, N'400271', N'620186', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'40042188', N'553400', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Corey Frank', N'Bel Air', NULL, NULL, NULL, N'413103', N'617638', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Wesley Scoggin', N'Roseville', NULL, NULL, NULL, N'40044348', N'669543', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Kevin Duffy', N'Sacramento', NULL, NULL, NULL, N'40046196', N'633479', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'James Moore', N'Lawrence', NULL, NULL, NULL, N'40048909', N'660651', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Sean Murray', N'Sacramento', NULL, NULL, NULL, N'40048957', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Michael Bubel', N'Houston', NULL, NULL, NULL, N'40052332', N'553400', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Michael Demko', N'Campbell', NULL, NULL, NULL, N'520451', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Matt De Garmo', N'Walnut Creek', NULL, NULL, NULL, N'40052504', N'603434', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Lisa Fulco', N'Bel Air', NULL, NULL, NULL, N'40055659', N'617638', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Robert Brennan', N'Redding', NULL, NULL, NULL, N'460981', N'669946', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 0, NULL, 0, NULL, NULL, N'zzKimberly Caldwell', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'478532', N'678808', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Daravy Son', N'Manasquan', NULL, NULL, NULL, N'417136', N'678808', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Jessica Baumgartner', N'Manasquan', NULL, NULL, NULL, N'479487', N'678808', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Richard Looney', N'Manasquan', NULL, NULL, NULL, N'415100', N'678808', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Rob Giunco', N'Manasquan', NULL, NULL, NULL, N'479489', N'678808', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Chuck Alexander', N'Manasquan', NULL, NULL, NULL, N'479536', N'678808', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Matt Pulsipher', N'Vancouver', NULL, NULL, NULL, N'40058470', N'680264', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Robert McKelvey', N'Manasquan', NULL, NULL, NULL, N'479488', NULL, NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Britton Riley', N'Cincinnati', NULL, NULL, NULL, N'485498', N'666128', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Cali Visentin', N'Lawrence', NULL, NULL, NULL, N'574780', N'660651', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Renee Nenninger', N'St Louis', NULL, NULL, NULL, N'40062002', N'619680', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Jerod Yee', N'Folsom', NULL, NULL, NULL, N'40063877', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Rob Ryan', N'Yuba City', NULL, NULL, NULL, N'40058141', N'633523', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Tyler Collier', N'Chico', NULL, NULL, NULL, N'40105584', N'699159', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Tim Vanech', N'Boston', NULL, NULL, NULL, N'429167', N'699159', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Luis Raposo', N'Boston', NULL, NULL, NULL, N'429168', N'513340', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Davis Blomquist', N'Folsom', NULL, NULL, NULL, N'570088', N'679861', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Allison Scoggin', N'Roseville', NULL, NULL, NULL, N'40086387', N'702407', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Gavin Morrissey', N'Waltham', NULL, NULL, NULL, N'465543', NULL, NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Terry Muchler', N'Dansville', NULL, NULL, NULL, N'483395', N'680264', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Jeff Brooks', N'Vancouver', NULL, NULL, NULL, N'40081791', NULL, NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, N'Benjamin Knight (RPS-SIMPLE IRA)', NULL, NULL, N'Benjamin Knight', N'Chico', NULL, NULL, NULL, N'5312758', N'52350', NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, N'Brian Murphy/Blake Davelaar (Simple IRA)', NULL, NULL, N'Brian Murphy', N'Tucson', NULL, NULL, NULL, N'485721', NULL, NULL
    UNION ALL
SELECT N'American Funds - Advisory', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Brian Murphy', N'Tucson', NULL, NULL, NULL, N'426919', N'555052', NULL
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Adam Kint', N'Folsom', NULL, NULL, NULL, NULL, NULL, N'2732192'
    UNION ALL
SELECT N'Bloomwell 529', 0, NULL, 0, NULL, NULL, NULL, N'zzAndrew Kessler', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'6211526'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Andrew Shafer', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, N'3199300'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Austin McDaniel', N'Albuquerque', NULL, NULL, NULL, NULL, NULL, N'4063234'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Bob Sponseller', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, N'2176946'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Bret Butcher', N'Seattle', NULL, NULL, NULL, NULL, NULL, N'5257622'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Britton Riley', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, N'6431601'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Cheyenne Walker', N'Santa Rosa', NULL, NULL, NULL, NULL, NULL, N'4260856'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Daniel Novak', N'Bel Air', NULL, NULL, NULL, NULL, NULL, N'1316721'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'David Schauer', N'Sacramento', NULL, NULL, NULL, NULL, NULL, N'3086618'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Glenn Downs', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, N'1839892'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Michael Coates', N'Cincinnati', NULL, NULL, NULL, NULL, NULL, N'5397320'
    UNION ALL
SELECT N'Bloomwell 529', 0, NULL, 0, NULL, NULL, NULL, N'zzRichard Mayer', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, N'2206972'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Ted Smalling', N'Sacramento', NULL, NULL, NULL, NULL, NULL, N'5981078'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Matt De Garmo', N'Walnut Creek', NULL, NULL, NULL, NULL, NULL, N'BLW215019'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, N'25799'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, N'A6GJ'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Unassigned', NULL, NULL, NULL, NULL, NULL, NULL, N'AXL7'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Lisa Fulco', N'Bel Air', NULL, NULL, NULL, NULL, NULL, N'2630703'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Paul Culbertson', N'Houston', NULL, NULL, NULL, NULL, NULL, N'5417086'
    UNION ALL
SELECT N'Bloomwell 529', 1, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, N'Allegra Swan', N'Campbell', NULL, NULL, NULL, NULL, NULL, N'BLW215062';
END
GO
