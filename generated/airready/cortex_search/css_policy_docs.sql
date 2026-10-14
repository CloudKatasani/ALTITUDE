-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/airready/cortex_templates.yaml. Regenerate with `altitude generate`.
CREATE OR REPLACE CORTEX SEARCH SERVICE DOCS.SEARCH.CSS_POLICY_DOCS
  ON CHUNK_TEXT
  ATTRIBUTES DOC_ID, DOC_TYPE, REGION, ACL_GROUP, EFFECTIVE_DATE
  WAREHOUSE = WH_AGENTS
  TARGET_LAG = '1 hour'
  EMBEDDING_MODEL = 'snowflake-arctic-embed-l-v2.0'
  COMMENT = 'Governed policy and procedure documents, chunked; ACL group per chunk mirrors the source system.'
  AS (
    SELECT CHUNK_TEXT, DOC_ID, DOC_TYPE, REGION, ACL_GROUP, EFFECTIVE_DATE
    FROM DOCS.CURATED.POLICY_CHUNKS
  );
