-- PlanEngine-owned Azure Synapse dedicated-pool schema. sfp/tho remain source-only.
-- Execute as a deployment principal with schema/table/RLS DDL permission.

IF SCHEMA_ID(N'planengine') IS NULL
    EXEC(N'CREATE SCHEMA [planengine]');
GO

IF SCHEMA_ID(N'planengine_security') IS NULL
    EXEC(N'CREATE SCHEMA [planengine_security]');
GO

IF OBJECT_ID(N'[planengine].[households]', N'U') IS NULL
CREATE TABLE [planengine].[households] (
    [id] varchar(36) NOT NULL,
    [name] nvarchar(255) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [facts_json] nvarchar(max) NOT NULL,
    [updated_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = ROUND_ROBIN, HEAP);
GO

IF OBJECT_ID(N'[planengine].[facts_versions]', N'U') IS NULL
CREATE TABLE [planengine].[facts_versions] (
    [id] varchar(36) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [snapshot_json] nvarchar(max) NOT NULL,
    [created_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = ROUND_ROBIN, HEAP);
GO

IF OBJECT_ID(N'[planengine].[scenarios]', N'U') IS NULL
CREATE TABLE [planengine].[scenarios] (
    [id] varchar(36) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [name] nvarchar(255) NOT NULL,
    [base_facts_version_id] varchar(36) NOT NULL,
    [overrides_json] nvarchar(max) NOT NULL,
    [is_recommended] bit NOT NULL,
    [created_at] datetime2 NOT NULL,
    [updated_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = ROUND_ROBIN, HEAP);
GO

IF OBJECT_ID(N'[planengine].[portal_records]', N'U') IS NULL
CREATE TABLE [planengine].[portal_records] (
    [id] varchar(36) NOT NULL,
    [household_id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [kind] nvarchar(40) NOT NULL,
    [payload_json] nvarchar(max) NOT NULL,
    [created_at] datetime2 NOT NULL,
    [updated_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = ROUND_ROBIN, HEAP);
GO

IF OBJECT_ID(N'[planengine].[audit_log]', N'U') IS NULL
CREATE TABLE [planengine].[audit_log] (
    [id] varchar(36) NOT NULL,
    [firm_id] nvarchar(255) NOT NULL,
    [actor] nvarchar(320) NOT NULL,
    [action] nvarchar(80) NOT NULL,
    [entity_id] varchar(36) NOT NULL,
    [payload_json] nvarchar(max) NOT NULL,
    [created_at] datetime2 NOT NULL
) WITH (DISTRIBUTION = ROUND_ROBIN, HEAP);
GO

-- A middle-tier connection sets firm_id with sp_set_session_context. Synapse
-- supports FILTER predicates (but not BLOCK predicates), so this policy is
-- paired with mandatory firm_id predicates and bound insert values in the app.
IF OBJECT_ID(N'[planengine_security].[fn_firm_access]', N'IF') IS NULL
    EXEC(N'
        CREATE FUNCTION [planengine_security].[fn_firm_access]
            (@firm_id nvarchar(255))
        RETURNS TABLE
        WITH SCHEMABINDING
        AS
        RETURN SELECT 1 AS [allowed]
        WHERE @firm_id = CAST(SESSION_CONTEXT(N''firm_id'') AS nvarchar(255));
    ');
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.security_policies
    WHERE [name] = N'firm_isolation_policy'
      AND [schema_id] = SCHEMA_ID(N'planengine_security')
)
    EXEC(N'
        CREATE SECURITY POLICY [planengine_security].[firm_isolation_policy]
        ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
            ON [planengine].[households],
        ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
            ON [planengine].[facts_versions],
        ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
            ON [planengine].[scenarios],
        ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
            ON [planengine].[portal_records],
        ADD FILTER PREDICATE [planengine_security].[fn_firm_access]([firm_id])
            ON [planengine].[audit_log]
        WITH (STATE = ON);
    ');
GO

-- Grant the runtime identity least-privilege SELECT/INSERT/UPDATE/DELETE on the
-- planengine schema and SELECT/REFERENCES on fn_firm_access outside this script.
-- Do not grant UPDATE or DELETE on audit_log; append_audit needs INSERT only.
