-- meta.Data_Dictionary_* — single source of truth for warehouse metadata.
-- Consumed by the wealth-mcp semantic layer and the Data Catalog web app.
-- Generated/loaded by backend/catalog/sql_publish.py from the catalog data.
--
-- Target: Azure Synapse DEDICATED SQL pool (DataWarehouse).
-- Notes on dialect:
--   * Small, read-mostly reference tables -> DISTRIBUTION = REPLICATE, HEAP.
--   * Dedicated pool does not support CREATE TABLE IF NOT EXISTS, so we
--     DROP TABLE IF EXISTS then CREATE (the publisher wraps this in a load).
--   * PK/FK are not enforced by the engine; declared NOT ENFORCED for lineage.
--   * The `meta` schema is created by sql_publish.py before this script runs.

IF OBJECT_ID('meta.Data_Dictionary_Table', 'U') IS NOT NULL DROP TABLE meta.Data_Dictionary_Table;
CREATE TABLE meta.Data_Dictionary_Table (
    table_id         NVARCHAR(128)  NOT NULL,
    table_name       NVARCHAR(256)  NOT NULL,
    schema_name      NVARCHAR(64)   NULL,
    db_name          NVARCHAR(128)  NULL,
    db_table         NVARCHAR(256)  NULL,
    guid             NVARCHAR(64)   NULL,
    business_name    NVARCHAR(256)  NULL,
    grain            NVARCHAR(512)  NULL,
    pk               NVARCHAR(256)  NULL,
    domain           NVARCHAR(128)  NULL,
    synonyms         NVARCHAR(1024) NULL,
    deprecated       BIT            NOT NULL DEFAULT 0,
    spotter_enabled  BIT            NOT NULL DEFAULT 0,
    [description]    NVARCHAR(MAX)  NULL,
    notes            NVARCHAR(MAX)  NULL,
    worksheets       NVARCHAR(2048) NULL,
    column_count     INT            NULL,
    source           NVARCHAR(32)   NULL,
    generated_at     DATETIME2(0)   NULL
)
WITH (DISTRIBUTION = REPLICATE, HEAP);
GO

IF OBJECT_ID('meta.Data_Dictionary_Column', 'U') IS NOT NULL DROP TABLE meta.Data_Dictionary_Column;
CREATE TABLE meta.Data_Dictionary_Column (
    table_id              NVARCHAR(128)  NOT NULL,
    table_name            NVARCHAR(256)  NOT NULL,
    schema_name           NVARCHAR(64)   NULL,
    db_table              NVARCHAR(256)  NULL,
    db_column_name        NVARCHAR(256)  NULL,
    display_name          NVARCHAR(256)  NULL,
    data_type             NVARCHAR(64)   NULL,
    kind                  NVARCHAR(32)   NULL,
    aggregation           NVARCHAR(32)   NULL,
    synonyms              NVARCHAR(1024) NULL,
    [description]         NVARCHAR(MAX)  NULL,
    pii                   BIT            NOT NULL DEFAULT 0,
    hot                   BIT            NOT NULL DEFAULT 0,
    derivation_expression NVARCHAR(MAX)  NULL,
    source_notebook       NVARCHAR(256)  NULL,
    source_systems        NVARCHAR(512)  NULL,
    generated_at          DATETIME2(0)   NULL
)
WITH (DISTRIBUTION = REPLICATE, HEAP);
GO

IF OBJECT_ID('meta.Data_Dictionary_Join', 'U') IS NOT NULL DROP TABLE meta.Data_Dictionary_Join;
CREATE TABLE meta.Data_Dictionary_Join (
    from_table   NVARCHAR(256)  NULL,
    from_id      NVARCHAR(128)  NULL,
    to_table     NVARCHAR(256)  NULL,
    to_id        NVARCHAR(128)  NULL,
    from_col     NVARCHAR(256)  NULL,
    to_col       NVARCHAR(256)  NULL,
    join_type    NVARCHAR(32)   NULL,
    one_to_one   BIT            NOT NULL DEFAULT 0,
    join_name    NVARCHAR(256)  NULL,
    generated_at DATETIME2(0)   NULL
)
WITH (DISTRIBUTION = REPLICATE, HEAP);
GO

IF OBJECT_ID('meta.Data_Dictionary_Glossary', 'U') IS NOT NULL DROP TABLE meta.Data_Dictionary_Glossary;
CREATE TABLE meta.Data_Dictionary_Glossary (
    term         NVARCHAR(256)  NOT NULL,
    definition   NVARCHAR(MAX)  NULL,
    generated_at DATETIME2(0)   NULL
)
WITH (DISTRIBUTION = REPLICATE, HEAP);
GO
