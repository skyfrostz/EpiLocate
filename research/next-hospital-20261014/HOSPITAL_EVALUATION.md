# Hospital evaluation checklist — planned, not executed

Owner: 钟佳桦. Intended window: 2026-10-15 through 2026-10-17 (Asia/Shanghai).
No hospital enrollment, clinical approval, data transfer or diagnosis is recorded
by this document. The hospital's approved collection and research process must
define eligibility, consent/authorization, storage and permitted users first.

1. Record the approved task and label definitions separately: case diagnosis,
   imaging abnormality, infection-related abnormality, and lesion reference.
   Preserve unknowns. COVID-negative is not synonymous with a normal chest CT.
2. Retain complete deidentified series under approved local custody. Preserve
   Study/Series/SOP linkage, geometry and a private identifier mapping according
   to the hospital's process. Do not upload images to public Git or third-party
   services. No tool in this package performs clinical upload.
3. Assign patient-level development and independent evaluation roles before
   looking at model results. Do not repurpose the existing sealed test/GT group.
4. Have doctors review and annotate independently before displaying AI. Record
   reviewed series/SOP range, target class, multiple objects, coverage/completeness,
   annotation version, and whether any AI output was previously visible.
5. Save initial independent annotation and subsequent AI-assisted revisions as
   separate immutable versions. An opinion about a demo is not independent GT.
6. Verify native image overlay, mask round trip and the exact SOP association.
   Record failed or ambiguous geometry; do not score those as normal cases.
7. Freeze candidate/model/config/hash, task definition, common support domain and
   5/10/20% budget rules before comparative scoring. Report E1/E2 and F0/F1
   separately, patient-level denominators, all failures and abstentions.
8. With incomplete annotation report observed-reference coverage and reviewed
   error locations; withhold complete-lesion recall, whole-lung precision and
   whole-volume Dice. Use complete-reference metrics only for qualified scope.
9. Label a display as LIVE computation or PRECOMPUTED results with exact run
   provenance. Show uncalibrated model scores as such, and clearly distinguish
   candidate absence, numerical failure, unsupported input and clinical normality.
10. Before demonstration, perform three repeats on the frozen approved inputs,
    verify saved asset hashes and coordinate overlays, test known failure states,
    and retain the previous version and precomputed results for offline fallback.

Planned annotation record fields: private patient key; Study/Series/SOP keys;
annotation schema/version; reviewer role; independent/AI-assisted phase; target
definition; review coverage; completeness; original polygon/object IDs; native
coordinate convention; clinical adjudication state; creation time; source hash.
This field list is a specification, not a claim that a clinical annotation
application or institutionally approved protocol has been delivered.
