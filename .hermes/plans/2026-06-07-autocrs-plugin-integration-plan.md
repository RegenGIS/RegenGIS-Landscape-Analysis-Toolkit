# AutoCRS Integration into RegenGIS Processing Plugin — Implementation Plan

> **For Hermes:** Use the `subagent-driven-development` and `opencode` skills to execute this plan phase-by-phase. Prefer one fresh worker per task. Keep the AutoCRS core as a plugin-internal capability, then expose thin Processing algorithms on top.

**Goal:** Add AutoCRS to the RegenGIS processing plugin as a reusable internal preparation layer that automatically chooses a suitable metric analysis CRS and prepares raster inputs for reliable spatial analysis, starting with explicit data-preparation tools and then integrating into selected existing algorithms.

**Architecture:** Split the current experimental AutoCRS script into (1) a pure heuristics module, (2) a QGIS-aware selector module with simplified caching, and (3) a raster-preparation module. Expose phase-1 functionality via new algorithms under `algorithms/0 data preperation/`, then integrate the preparation layer into existing raster-analysis algorithms beginning with `height_contours.py`.

**Tech Stack:** QGIS Processing plugin, PyQGIS, GDAL/GRASS via `processing.run`, Python dataclasses, plugin-local JSON cache, Hermes + OpenCode for phased implementation.

---

## Source context and constraints

### Existing relevant files
- Experimental AutoCRS code:
  - `/media/sf_hermes_input/qgis/autocrs/suitable_crs_heuristics.py`
  - `/media/sf_hermes_input/qgis/autocrs/suitable_crs_checker.py`
  - `/media/sf_hermes_input/qgis/autocrs/tests/test_suitable_crs_heuristics.py`
  - `/media/sf_hermes_input/qgis/autocrs/tests/test_catalog_ranking.py`
- Plugin code:
  - `/media/sf_hermes_input/qgis/regengis_processing_plugin/processing_provider.py`
  - `/media/sf_hermes_input/qgis/regengis_processing_plugin/plugin.py`
  - `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/1 Landscape/height_contours.py`
  - `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/2 Hydrology/twi.py`
  - `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/2 Hydrology/water_flow.py`
  - `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/3 microclimates/solar_radiation.py`

### High-level design rules
1. Do **not** keep AutoCRS as a loose multi-file Processing script architecture.
2. Do **not** make Processing scripts call other Processing scripts for code reuse.
3. Do keep AutoCRS as a plugin-internal Python package that normal plugin algorithms import.
4. Do keep catalog-first CRS selection; this is what makes AutoCRS globally useful and better than UTM-only shortcuts.
5. Do keep caching only where it helps: the catalog index layer.
6. Do use layer extent as the basis for recommendation; avoid `iface.mapCanvas()` as the core execution path.
7. Do phase rollout: visible prep tools first, automatic integration second.

### Known technical risk to address early
`processing_provider.py` currently dynamically imports algorithm modules with `spec.loader.exec_module(module)` but does not register them in `sys.modules` first. This can re-trigger the dataclass import bug already seen in the experimental AutoCRS script.

### Git note
The repo currently reports `dubious ownership` from this environment. Before implementation that needs git, either fix safe.directory or work without git in this environment.

---

# Phase 0 — Stabilize the plugin loading foundation

**Purpose:** Prevent the plugin’s dynamic module loading from reintroducing the same import/`dataclass` failures already solved in the experimental script.

## Deliverables
- Hardened `processing_provider.py` loader
- Optional lightweight import smoke check script or notes

### Task 0.1: Patch provider module loading to register modules in `sys.modules`

**Objective:** Ensure dynamically imported algorithm modules are registered before `exec_module()`.

**Files:**
- Modify: `/media/sf_hermes_input/qgis/regengis_processing_plugin/processing_provider.py`

**Implementation details:**
- Add `import sys`
- In `_load_algorithm_from_path`, after `module = importlib.util.module_from_spec(spec)`, insert:
  - `sys.modules[module_name] = module`
- Wrap `spec.loader.exec_module(module)` in `try/except`
- On exception: `sys.modules.pop(module_name, None)` then re-raise

**Verification:**
- Syntax check the file
- Confirm existing algorithms still import successfully
- Specifically note that this change is required before adding new dataclass-based AutoCRS modules

### Task 0.2: Decide import style for new AutoCRS modules

**Objective:** Standardize imports for all new plugin-internal AutoCRS code.

**Files:**
- Planning decision only, then reflected in future files

**Decision:**
- Use package-relative imports inside the plugin, e.g.:
  - `from ...autocrs.selector import recommend_metric_crs_for_layer`
  - or equivalent relative form appropriate to final module placement

**Verification:**
- New modules must import under the plugin provider, not only in standalone Python

---

# Phase 1 — Extract the AutoCRS core into plugin modules

**Purpose:** Move reusable logic into plugin-internal modules and remove script-hosting baggage.

## New files to create
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/autocrs/__init__.py`
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/autocrs/heuristics.py`
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/autocrs/selector.py`
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/autocrs/prepare.py`
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/autocrs/temp_layers.py`

## Module responsibilities

### `autocrs/heuristics.py`
Contains only the pure or near-pure heuristics layer.

**Move from `suitable_crs_heuristics.py`:**
- `NationalGridSpec`
- `NATIONAL_GRID_SPECS`
- `Extent`
- `MetricCrsChoice`
- `normalize_longitude`
- `normalize_longitude_for_zone`
- `utm_zone_from_longitude`
- `utm_epsg`
- `utm_description`
- `ups_description`
- `utm_proj4`
- `custom_local_metric_proj`
- `choose_metric_crs`

**Leave behind:**
- any script-loader compatibility logic
- any caching logic
- any QGIS imports

### `autocrs/selector.py`
Contains the QGIS-aware catalog-first selector and the **only** remaining AutoCRS cache.

**Move from `suitable_crs_checker.py`:**
- `CatalogCandidate`
- `CatalogIndexEntry`
- `CatalogPreCandidate`
- `_safe_bbox_area`
- `_BoundsProxy`
- `_extent_matches_bounds`
- `_specificity_rank`
- `_epsg_from_authid`
- `_is_metric_projected_crs`
- `_crs_transform_from_wgs84`
- `_max_scale_factor_over_extent_with_transform`
- `_catalog_index`
- `_catalog_pre_candidate`
- `_catalog_candidate_from_pre`
- `_candidate_pre_rank_key`
- `_select_best_catalog_crs`
- `_candidate_to_choice`
- `_choice_to_qgis_crs`

**Refactor into public APIs:**
- `recommend_metric_crs_for_extent(extent_wgs84, feedback=None)`
- `recommend_metric_crs_for_layer(layer, feedback=None)`
- `qgis_crs_from_recommendation(recommendation)` if helpful

**Create new dataclass:**
- `AutoCrsRecommendation`
  - `authid`
  - `description`
  - `proj4`
  - `epsg`
  - `strategy`
  - `distortion_ppm`
  - `is_utm_or_ups`

**Keep caching in v1:**
- in-memory `_CATALOG_INDEX_CACHE`
- simple persistent JSON cache

**Simplify cache behavior:**
- one plugin-local cache directory only, e.g. `regengis_processing_plugin/.autocrs-cache/`
- cache identity only needs:
  - cache schema version
  - QGIS version token
- remove bootstrap cache export/import and multi-path search complexity

**Do not carry over to v1:**
- `_candidate_helper_paths()`
- `_load_heuristics_symbols()`
- `_InlineHeuristics`
- bootstrap cache shipping logic
- Script Editor fallback path logic
- `iface.mapCanvas()` recommendation path
- `@alg` decorator entrypoint

### `autocrs/prepare.py`
Introduces the analysis-preparation layer used by algorithms.

**New public helpers:**
- `extent_in_wgs84_for_layer(layer)`
- `recommend_analysis_crs_for_layer(layer, feedback=None)`
- `layer_needs_reprojection(layer, target_crs)`
- `prepare_raster_for_analysis(layer, context, feedback, target_crs=None, auto_select=True, output=None)`

**Create new dataclass:**
- `PreparedRaster`
  - `layer_or_path`
  - `source_crs_authid`
  - `target_crs_authid`
  - `was_reprojected`
  - `recommendation`
  - optional pixel size metadata

**Expected behavior:**
- read raster extent + CRS from the input layer
- compute WGS84 extent
- ask `selector.py` for best analysis CRS
- reproject only when needed
- return a prepared raster descriptor that algorithms can consume

### `autocrs/temp_layers.py`
Small utilities only.

**Helpers to add:**
- temporary output naming
- stable temporary layer labels
- path/name helpers if needed

---

# Phase 2 — Add explicit AutoCRS tools under `0 data preperation`

**Purpose:** Make AutoCRS visible, testable, and understandable before silently changing existing analysis behavior.

## New algorithm files
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/0 data preperation/recommend_analysis_crs.py`
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/0 data preperation/prepare_raster_for_analysis.py`

### Task 2.1: Implement `recommend_analysis_crs.py`

**Objective:** Expose the recommendation engine as a user-facing Processing algorithm.

**Inputs:**
- Prefer: one input layer parameter
- If a generic layer parameter becomes awkward in the current plugin conventions, start with raster input first

**Outputs:**
- chosen CRS authid
- CRS description
- PROJ string
- strategy
- distortion ppm
- is UTM/UPS boolean

**Behavior:**
- inspect input layer extent and CRS
- transform extent to WGS84
- call `recommend_metric_crs_for_layer(...)`
- return recommendation outputs
- push useful feedback text to explain what was chosen and why

**UX rule:**
- explain in user language: “RegenGIS selected a suitable metric analysis CRS automatically.”
- do not force the user into manual CRS concepts unless necessary

### Task 2.2: Implement `prepare_raster_for_analysis.py`

**Objective:** Expose raster preparation as a user-facing Processing algorithm.

**Inputs:**
- input raster
- auto-select boolean, default `True`
- optional manual target CRS override for advanced users
- optional resampling parameter if needed in v1, otherwise hardcode a safe initial choice and document it
- output raster destination

**Outputs:**
- output raster
- output target CRS
- source CRS
- was reprojected boolean
- optional strategy/description outputs if useful

**Behavior:**
- call `prepare_raster_for_analysis(...)`
- return the prepared raster
- clearly report whether reprojection happened

**Important design note:**
- This tool is not just a convenience wrapper; it is the visible preflight representation of how AutoCRS works in RegenGIS.

---

# Phase 3 — Integrate AutoCRS into one existing algorithm first

**Purpose:** Prove the pattern in one low-risk, high-value algorithm before touching the hydrology stack.

## First integration target
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/1 Landscape/height_contours.py`

### Why this first
- raster-based
- conceptually simple
- high confidence that a suitable projected CRS helps
- lower complexity than GRASS hydrology flows

### Task 3.1: Wire prepared raster into `height_contours.py`

**Objective:** Make contour generation operate on analysis-prepared raster input.

**Changes:**
- before the first raster step, prepare the input DTM through AutoCRS
- replace direct use of `parameters['digital_terrain_model_dtm']` with the prepared raster output in downstream processing steps
- add feedback messages describing the CRS preparation step

**New parameter choice:**
Choose one of these for v1:
1. no user-facing toggle yet; always prepare automatically
2. add `AUTO_SELECT_ANALYSIS_CRS` default `True`

**Recommendation:**
- For v1, add the toggle but default it to `True`
- This preserves trust and gives a recovery path for advanced users

**Verification:**
- confirm output still generates
- confirm output CRS is the chosen analysis CRS
- confirm the algorithm behaves the same when input is already in a suitable projected CRS

---

# Phase 4 — Integrate into hydrology algorithms

**Purpose:** Extend the proven pattern to the algorithms that most benefit from metric projected inputs.

## Targets
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/2 Hydrology/twi.py`
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/2 Hydrology/water_flow.py`

### Task 4.1: Integrate into `twi.py`

**Objective:** Ensure TWI runs on prepared raster in a suitable analysis CRS.

**Changes:**
- same preparation pattern as `height_contours.py`
- keep the rest of the model logic intact where possible
- document that the DTM may be automatically prepared in a suitable projected coordinate system for accurate terrain analysis

### Task 4.2: Integrate into `water_flow.py`

**Objective:** Ensure water flow analysis runs on prepared raster in a suitable analysis CRS.

**Changes:**
- same preparation pattern as above
- watch carefully for raster resolution/resampling consequences

**Important review point:**
- hydrology is more sensitive to reprojection/resampling than simple contour extraction
- keep reprojection choices conservative
- document assumptions clearly in code comments and help text

---

# Phase 5 — Evaluate solar integration and broader rollout

**Purpose:** Delay more complex or less obvious integrations until the prep pattern is stable.

## Candidate target
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/algorithms/3 microclimates/solar_radiation.py`

### Task 5.1: Design review before implementation

**Objective:** Decide whether solar analysis should use the same analysis CRS prep path unchanged.

**Questions to answer before coding:**
- Does raster reprojection help or interfere with the specific `r.sun.insoltime` workflow?
- Should solar use the same target CRS policy as hydrology/contours?
- Is a separate preparation policy needed for solar workflows?

**Rule:**
- Do not integrate into `solar_radiation.py` until phases 1–4 are working and reviewed

---

# Testing and verification plan

## Unit-level / pure logic tests
Create or port tests for:
- national-grid preference (e.g. NL extent → EPSG:28992)
- UTM zone selection based on center longitude
- antimeridian handling
- polar UPS handling
- large-extent custom local metric fallback
- southern hemisphere UTM south flag

**Suggested file:**
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/tests/test_autocrs_heuristics.py`

## Selector/cache tests
Create tests for:
- bounds matching ranking
- catalog candidate ranking
- cache identity structure
- cache roundtrip serialization
- QGIS version mismatch invalidation behavior

**Suggested file:**
- `/media/sf_hermes_input/qgis/regengis_processing_plugin/tests/test_autocrs_selector.py`

## Plugin-level smoke checks
At minimum verify:
- provider can import all new AutoCRS modules
- new algorithms appear in the plugin provider
- `recommend_analysis_crs` returns stable recommendation outputs
- `prepare_raster_for_analysis` returns a raster and metadata
- `height_contours` still runs after integration

## Manual QGIS checks
Run in QGIS Desktop:
1. install/reload plugin
2. confirm new algorithms appear in `0 data preperation`
3. run recommendation tool on at least:
   - Netherlands raster extent
   - compact non-Europe extent
   - antimeridian-ish synthetic test if feasible
4. run prepare-raster tool and inspect resulting layer CRS
5. run `Height Contours` with AutoCRS enabled
6. only then move to hydrology tools

---

# OpenCode execution strategy

## Working model
Use OpenCode for bounded implementation chunks, not for the whole migration at once.

## Recommended collaboration pattern
For each phase:
1. Hermes prepares the exact task brief
2. OpenCode implements one bounded slice in the repo
3. Hermes reviews diff + tests + architecture fit
4. Fix loop if needed
5. Move to next phase only after explicit pass

## Good OpenCode task boundaries
- Phase 0 provider hardening only
- Phase 1 extraction of `heuristics.py` only
- Phase 1 extraction of `selector.py` only
- Phase 2 `recommend_analysis_crs.py` only
- Phase 2 `prepare_raster_for_analysis.py` only
- Phase 3 `height_contours.py` integration only
- Phase 4 `twi.py` integration only
- Phase 4 `water_flow.py` integration only

## Bad OpenCode task boundaries
- “Integrate all of AutoCRS into the plugin”
- “Refactor everything and update all algorithms”
- “Fix all projection issues everywhere”

## OpenCode prompt shape
Each phase handoff should contain:
- exact files to modify/create
- exact functions to move or create
- explicit “do not touch” files
- required tests/verifications
- success criteria

---

# Phase gates

## Gate A — after Phase 0
Proceed only if:
- provider loader is hardened
- no import regressions introduced

## Gate B — after Phase 1
Proceed only if:
- pure heuristics and selector are separated cleanly
- no script-editor fallback baggage remains in plugin modules
- cache behavior is simplified and documented

## Gate C — after Phase 2
Proceed only if:
- both user-facing prep algorithms load
- recommendation outputs make sense
- raster preparation can complete in plugin context

## Gate D — after Phase 3
Proceed only if:
- `height_contours.py` works with prepared raster input
- CRS handling is understandable in feedback/help text

## Gate E — after Phase 4
Proceed only if:
- TWI and Water Flow still run end-to-end
- reprojection choices do not obviously degrade outputs

---

# Task list for phased execution

## Phase 0
1. Harden `processing_provider.py` dynamic import path
2. Verify existing algorithms still load

## Phase 1
3. Create `autocrs/__init__.py`
4. Create `autocrs/heuristics.py` from `suitable_crs_heuristics.py`
5. Create `autocrs/selector.py` from `suitable_crs_checker.py` selector logic
6. Simplify cache layout to plugin-local cache only
7. Create `autocrs/prepare.py`
8. Create `autocrs/temp_layers.py`
9. Add/port tests for heuristics and selector

## Phase 2
10. Create `algorithms/0 data preperation/recommend_analysis_crs.py`
11. Create `algorithms/0 data preperation/prepare_raster_for_analysis.py`
12. Verify provider registration and manual QGIS visibility

## Phase 3
13. Integrate AutoCRS prep into `height_contours.py`
14. Verify contour workflow with and without reprojection

## Phase 4
15. Integrate AutoCRS prep into `twi.py`
16. Integrate AutoCRS prep into `water_flow.py`
17. Verify hydrology outputs and performance

## Phase 5
18. Evaluate `solar_radiation.py` for later integration
19. Decide whether separate solar policy is needed

---

# Success criteria

The implementation is successful when:
- AutoCRS exists as a plugin-internal package, not a loose script system
- the plugin can recommend a suitable metric analysis CRS from a layer extent
- the plugin can prepare raster inputs into a suitable analysis CRS
- at least one production algorithm (`height_contours.py`) uses AutoCRS successfully
- hydrology tools can be migrated in a second controlled wave
- users do not need to understand CRS theory to get correct metric analysis behavior

---

# Recommended next execution step

Start with **Phase 0 only**.

That is the smallest, highest-leverage first move because it removes a known module-loading risk before any AutoCRS package files are introduced.
