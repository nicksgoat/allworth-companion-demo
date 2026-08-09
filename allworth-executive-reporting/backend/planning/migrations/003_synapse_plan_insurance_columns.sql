-- Adds normalized life-insurance fields to the PlanEngine publication mart.
-- policy_json remains the full-fidelity source for fields not promoted here.

IF NOT EXISTS (
    SELECT 1
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = N'planengine'
      AND TABLE_NAME = N'published_plan_insurance'
      AND COLUMN_NAME = N'policy_number'
)
    ALTER TABLE [planengine].[published_plan_insurance] ADD
        [policy_number] nvarchar(120) NULL,
        [institution] nvarchar(255) NULL,
        [purchase_date] date NULL,
        [policy_type] nvarchar(80) NULL,
        [insured] nvarchar(60) NULL,
        [owner] nvarchar(60) NULL,
        [beneficiary] nvarchar(255) NULL,
        [contingent_beneficiary] nvarchar(255) NULL,
        [current_cash_value] decimal(19,4) NULL,
        [basis] decimal(19,4) NULL,
        [cash_value_growth_rate] decimal(19,10) NULL,
        [term_years] int NULL,
        [term_ends_at_retirement] bit NULL,
        [premium_term_years] int NULL,
        [premium_payer] nvarchar(60) NULL,
        [under_our_management] bit NULL,
        [exclude_from_planning] bit NULL;
GO
