-- PlanEngine publication mart for approved plans.
-- Rendered by backend/scripts/migrate_synapse.py into the configured schema.
-- sfp/tho/tav remain source-only; these tables are PlanEngine-owned.

IF OBJECT_ID(N'[planengine].[published_plans]', N'U') IS NULL
CREATE TABLE [planengine].[published_plans] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [source_household_id] nvarchar(80) NULL,
    [household_name] nvarchar(255) NOT NULL,
    [facts_version_id] varchar(36) NOT NULL,
    [scenario_id] varchar(36) NOT NULL,
    [scenario_name] nvarchar(255) NOT NULL,
    [status] nvarchar(40) NOT NULL,
    [published_at] datetime2 NOT NULL,
    [published_by] nvarchar(320) NOT NULL,
    [superseded_by_publication_id] varchar(36) NULL,
    [withdrawn_at] datetime2 NULL,
    [withdrawn_by] nvarchar(320) NULL,
    [idempotency_key] nvarchar(128) NOT NULL,
    [input_hash] varchar(64) NOT NULL,
    [result_hash] varchar(64) NOT NULL,
    [summary_json] nvarchar(max) NOT NULL,
    [advisor_note] nvarchar(max) NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_people]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_people] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [person_id] varchar(36) NOT NULL,
    [source_person_id] nvarchar(80) NULL,
    [role] nvarchar(60) NOT NULL,
    [first_name] nvarchar(120) NULL,
    [last_name] nvarchar(120) NULL,
    [date_of_birth] date NULL,
    [retirement_age] int NULL,
    [assumed_age_of_death] int NULL,
    [email_hash] varchar(64) NULL,
    [source] nvarchar(120) NULL,
    [observed_at] datetime2 NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_accounts]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_accounts] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [account_id] varchar(36) NOT NULL,
    [source_account_id] nvarchar(80) NULL,
    [external_account_number] nvarchar(80) NULL,
    [name] nvarchar(255) NOT NULL,
    [kind] nvarchar(60) NOT NULL,
    [owner] nvarchar(60) NOT NULL,
    [current_value] decimal(19,4) NOT NULL,
    [tax_basis] decimal(19,4) NULL,
    [growth_rate] decimal(19,10) NULL,
    [income_yield] decimal(19,10) NULL,
    [tax_exempt_yield] decimal(19,10) NULL,
    [liquidity] int NULL,
    [apply_rmd] bit NOT NULL,
    [exclude_from_planning] bit NOT NULL,
    [source] nvarchar(120) NULL,
    [observed_at] datetime2 NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_holdings]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_holdings] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [account_id] varchar(36) NOT NULL,
    [external_account_number] nvarchar(80) NULL,
    [symbol] nvarchar(80) NULL,
    [cusip] nvarchar(32) NULL,
    [description] nvarchar(500) NOT NULL,
    [security_type] nvarchar(120) NULL,
    [asset_class] nvarchar(160) NOT NULL,
    [sector] nvarchar(160) NULL,
    [quantity] decimal(28,8) NOT NULL,
    [current_price] decimal(19,6) NOT NULL,
    [market_value] decimal(19,4) NOT NULL,
    [cost_basis] decimal(19,4) NULL,
    [weight] decimal(19,10) NULL,
    [as_of_date] date NULL,
    [source] nvarchar(120) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), CLUSTERED COLUMNSTORE INDEX);
GO

IF OBJECT_ID(N'[planengine].[published_plan_liabilities]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_liabilities] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [liability_id] varchar(36) NOT NULL,
    [source_liability_id] nvarchar(80) NULL,
    [institution] nvarchar(255) NOT NULL,
    [loan_type] nvarchar(80) NULL,
    [current_balance] decimal(19,4) NOT NULL,
    [interest_rate] decimal(19,10) NOT NULL,
    [term_years] int NOT NULL,
    [payment_frequency] nvarchar(40) NOT NULL,
    [repayment_type] nvarchar(40) NOT NULL,
    [source] nvarchar(120) NULL,
    [observed_at] datetime2 NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_cashflows]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_cashflows] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [cashflow_id] varchar(36) NOT NULL,
    [source_cashflow_id] nvarchar(80) NULL,
    [flow_group] nvarchar(20) NOT NULL,
    [name] nvarchar(255) NOT NULL,
    [kind] nvarchar(80) NOT NULL,
    [owner] nvarchar(60) NOT NULL,
    [amount] decimal(19,4) NOT NULL,
    [taxable] bit NOT NULL,
    [required] bit NOT NULL,
    [starts_json] nvarchar(max) NULL,
    [ends_json] nvarchar(max) NULL,
    [indexing_json] nvarchar(max) NULL,
    [source] nvarchar(120) NULL,
    [observed_at] datetime2 NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_goals]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_goals] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [goal_ordinal] int NOT NULL,
    [goal_id] varchar(36) NULL,
    [name] nvarchar(255) NOT NULL,
    [target_amount] decimal(19,4) NULL,
    [target_year] int NULL,
    [priority] nvarchar(40) NULL,
    [goal_json] nvarchar(max) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_insurance]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_insurance] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [policy_id] varchar(36) NOT NULL,
    [source_policy_id] nvarchar(80) NULL,
    [policy_name] nvarchar(255) NOT NULL,
    [current_death_benefit] decimal(19,4) NOT NULL,
    [annual_premium] decimal(19,4) NOT NULL,
    [policy_json] nvarchar(max) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_assumptions]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_assumptions] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [assumption_key] nvarchar(160) NOT NULL,
    [assumption_value] nvarchar(max) NOT NULL,
    [source] nvarchar(120) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_plan_years]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_years] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [plan_year] int NOT NULL,
    [client_age] int NULL,
    [spouse_age] int NULL,
    [phase] nvarchar(40) NOT NULL,
    [inflows] decimal(19,4) NOT NULL,
    [outflows] decimal(19,4) NOT NULL,
    [taxes] decimal(19,4) NOT NULL,
    [withdrawals] decimal(19,4) NOT NULL,
    [savings] decimal(19,4) NOT NULL,
    [investment_growth] decimal(19,4) NOT NULL,
    [net_worth] decimal(19,4) NOT NULL,
    [shortfall] decimal(19,4) NOT NULL,
    [estate_value] decimal(19,4) NULL
) WITH (DISTRIBUTION = HASH([household_id]), CLUSTERED COLUMNSTORE INDEX);
GO

IF OBJECT_ID(N'[planengine].[published_plan_account_years]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_account_years] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [plan_year] int NOT NULL,
    [account_id] varchar(36) NOT NULL,
    [balance] decimal(19,4) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), CLUSTERED COLUMNSTORE INDEX);
GO

IF OBJECT_ID(N'[planengine].[published_plan_liability_years]', N'U') IS NULL
CREATE TABLE [planengine].[published_plan_liability_years] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [plan_year] int NOT NULL,
    [liability_id] varchar(36) NOT NULL,
    [balance] decimal(19,4) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), CLUSTERED COLUMNSTORE INDEX);
GO

IF OBJECT_ID(N'[planengine].[published_estate_results]', N'U') IS NULL
CREATE TABLE [planengine].[published_estate_results] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [scenario_id] varchar(36) NOT NULL,
    [first_death_person] nvarchar(60) NULL,
    [first_death_age] int NULL,
    [gross_estate] decimal(19,4) NULL,
    [liabilities] decimal(19,4) NULL,
    [taxable_estate] decimal(19,4) NULL,
    [estate_tax] decimal(19,4) NULL,
    [liquidity_surplus] decimal(19,4) NULL,
    [result_json] nvarchar(max) NOT NULL,
    [created_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_monte_carlo_results]', N'U') IS NULL
CREATE TABLE [planengine].[published_monte_carlo_results] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [scenario_id] varchar(36) NOT NULL,
    [job_id] varchar(36) NULL,
    [n_trials] int NOT NULL,
    [seed] int NULL,
    [probability_of_success] decimal(9,8) NOT NULL,
    [cma_version] nvarchar(80) NOT NULL,
    [holdings_as_of] date NULL,
    [portfolio_expected_return] decimal(19,10) NULL,
    [portfolio_volatility] decimal(19,10) NULL,
    [input_snapshot_json] nvarchar(max) NOT NULL,
    [result_json] nvarchar(max) NOT NULL,
    [created_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF OBJECT_ID(N'[planengine].[published_monte_carlo_year_bands]', N'U') IS NULL
CREATE TABLE [planengine].[published_monte_carlo_year_bands] (
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [plan_year] int NOT NULL,
    [p5] decimal(19,4) NOT NULL,
    [p25] decimal(19,4) NOT NULL,
    [p50] decimal(19,4) NOT NULL,
    [p75] decimal(19,4) NOT NULL,
    [p95] decimal(19,4) NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), CLUSTERED COLUMNSTORE INDEX);
GO

IF OBJECT_ID(N'[planengine].[publication_events]', N'U') IS NULL
CREATE TABLE [planengine].[publication_events] (
    [id] varchar(36) NOT NULL,
    [publication_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [actor] nvarchar(320) NOT NULL,
    [action] nvarchar(80) NOT NULL,
    [payload_json] nvarchar(max) NOT NULL,
    [created_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = HASH([household_id]), HEAP);
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plans]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plans];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_people]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_people];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_accounts]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_accounts];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_holdings]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_holdings];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_liabilities]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_liabilities];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_cashflows]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_cashflows];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_goals]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_goals];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_insurance]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_insurance];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_assumptions]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_assumptions];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_years]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_years];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_account_years]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_account_years];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_plan_liability_years]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_plan_liability_years];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_estate_results]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_estate_results];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_monte_carlo_results]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_monte_carlo_results];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[published_monte_carlo_year_bands]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[published_monte_carlo_year_bands];
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.security_predicates
    WHERE [target_object_id] = OBJECT_ID(N'[planengine].[publication_events]')
)
    ALTER SECURITY POLICY [planengine_security].[firm_isolation_policy]
    ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
    ON [planengine].[publication_events];
GO

