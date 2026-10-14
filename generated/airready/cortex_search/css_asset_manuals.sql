-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/airready/cortex_templates.yaml. Regenerate with `altitude generate`.
CREATE OR REPLACE CORTEX SEARCH SERVICE DOCS.SEARCH.CSS_ASSET_MANUALS
  ON CHUNK_TEXT
  ATTRIBUTES ASSET_CLASS, MANUFACTURER, ACL_GROUP
  WAREHOUSE = WH_AGENTS
  TARGET_LAG = '1 day'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  COMMENT = 'Asset maintenance manuals for field operations (utilities use-case pack).'
  AS (
    SELECT CHUNK_TEXT, ASSET_CLASS, MANUFACTURER, ACL_GROUP
    FROM DOCS.CURATED.ASSET_MANUAL_CHUNKS
  );
