-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COMP-006 (14.4 compute, medium): Single-cluster warehouse queues at peak
-- threshold: rubric.compute.peak_queued_load_max; playbook: PB-COMP-SCALE-OUT; autonomy: L2
WITH h AS (SELECT WAREHOUSE_NAME, hour(START_TIME) AS HOD, avg(AVG_QUEUED_LOAD) AS Q
           FROM WAREHOUSE_LOAD_HISTORY GROUP BY 1, 2)
SELECT h.WAREHOUSE_NAME AS OBJECT_NAME, round(max(h.Q), 3) AS OBSERVED FROM h
JOIN WAREHOUSES w ON w.WAREHOUSE_NAME = h.WAREHOUSE_NAME
WHERE coalesce(w.MAX_CLUSTER_COUNT, 1) = 1
GROUP BY 1 HAVING max(h.Q) > $threshold ORDER BY 1;
