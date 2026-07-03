# Questions for Designers — Frontend/Backend/Data Integration

Context: the FastAPI gateway connecting the React dashboard to the DuckDB data is built and
working. A few contract details are still ambiguous. Answers to the questions below let us
finish the integration without guessing. Split by who each question is for.

===============================================================================
FOR THE FRONTEND DESIGNER (React dashboard)
===============================================================================

1) What fields go in each facility and department item?
   Your mockData.js defines shapes for KPIs, charts, etc., but there is no mock for
   /api/facilities or /api/departments, and App.jsx doesn't render them yet. So I don't
   know the exact object shape you want.
   Right now I return:
       facilities:  [{ id, name }]
       departments: [{ id, name, facility_id }]
   Is that right, or do you want different field names (e.g. facility_id instead of id,
   or label instead of name)? Give me the exact keys so the dropdowns bind correctly.

2) What should each "view" (CEO / Factory / Department) actually show?
   The dashboard only sends ?view=ceo|factory|department. It never says WHICH facility or
   department. So when someone picks "Factory Manager," I don't know if that means "show one
   specific factory" or "show all factories, grouped." I need the rule for each view:
       - CEO                -> all facilities combined?
       - Factory Manager    -> one facility (which one? or does a dropdown pick it)?
       - Department Manager -> one department?
   Until confirmed, view is accepted but ignored (numbers are global).

3) Are you adding the missing pieces to client.js, or should the backend stay flexible?
   Two gaps in the committed frontend:
       - client.js has no getFacilities / getDepartments functions, but useScopeOptions.js
         imports them -> this will break `npm run build`.
       - client.js never sends facility_id or department_id, only view.
   The backend already accepts facility_id / department_id as optional filters, so I'm ready
   whenever you are. Confirm: are you wiring these on the frontend, or should scoping be
   handled another way?

4) What time window are the KPI "deltas" comparing against?
   Each KPI card shows a delta (the little up/down %). A delta is "now vs. some earlier
   point," but I don't know the earlier point. Last 24h vs. the 24h before? Today vs.
   yesterday? Also, our data is currently a single snapshot with no history, so deltas
   return 0 for now. Tell me the intended comparison period so it's ready once we have
   historical data.

5) Does "energy waste" mean wasted power, or total power cost?
   The KPI field is energy_waste_cost_inr. The database has two candidates:
       - estimated_power_waste_cost_inr : only the EXCESS/wasted power cost
                                          (non-zero when a machine is CRITICAL_POWER_WASTE)
       - operational_power_cost_inr     : the TOTAL power cost
   I mapped it to the WASTE one (matches the name). Confirm that's what the card should show.

===============================================================================
FOR THE DATA DESIGNER
===============================================================================

6) Database location (confirmation only - already resolved)
   The backend now reads data/database/operational_twin.db, table gold_operational_metrics
   (the one your gold-layer builder creates). Just flagging that this is the source of truth
   now - no action needed unless that changed.

7) Are there human-readable names for facilities and departments?
   The gold table only has IDs like CHENNAI_RECYCLING_PLANT and PRE_PROCESSING. Is there a
   lookup table with friendly display names ("Chennai Recycling Plant"), or should the
   dashboard just show the raw IDs?

8) Which column is the real "energy waste"?
   Same as #5, from your side: for reporting, should "energy waste" be
   estimated_power_waste_cost_inr (excess only) or operational_power_cost_inr (total)?
   I want the data and frontend definitions to agree.

9) Is the data a one-time snapshot, or will more keep arriving?
   Right now it's a fixed snapshot (a couple minutes of readings on July 2). Your builder
   globs sensor_data_*.json, which suggests more files might land over time. Which is it?
   This decides how I calculate "as of" timestamps and whether the period-over-period
   deltas (#4) will ever have history to compute against.

10) Any existing queries I should reuse?
    Did the financial-impact analytics work already produce SQL views or queries for things
    like waste-by-machine or top-events? If so, point me to them so I reuse your logic
    instead of re-deriving it (and risking a mismatch).
