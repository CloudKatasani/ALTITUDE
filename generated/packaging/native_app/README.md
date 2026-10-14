<!-- AUTO-GENERATED — DO NOT EDIT. Source: altitude.packaging.native_app (harvest contract + check catalogue). Regenerate with `altitude generate`. -->
# ALTITUDE D0 Snapshot (Native App)

Runs the D1–D5 diagnostic checks inside your Snowflake account. Nothing leaves the account: the app has
no external access integration and reads metadata only (no table rows).

1. Install from the listing and grant `IMPORTED PRIVILEGES ON SNOWFLAKE DB`.
2. Optionally insert intake values (contract price per credit, Tier-1 tables) into `HARVEST.CLIENT_INPUTS`.
3. `CALL CORE.HARVEST('ENTERPRISE', 90);` then `CALL CORE.RUN_D0();`
4. `SELECT * FROM CORE.TOP_FINDINGS;` — then ask ALTITUDE Partners for the evidence-backed Package D readout.
