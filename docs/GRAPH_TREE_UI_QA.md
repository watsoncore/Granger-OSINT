# Tree / Graph — Master Fix V2

Source and final frozen Qt WebEngine checks on 2026-11-02. Final EXE SHA-256:
`428f3d02060bf059573921c7d8e8cdd08cab11a70526cdbef4049473548d2077`.
These controls render previously collected real public evidence; they do not
claim that opening the visualization performs new source collection.

## Implementation

The common evidence graph remains intact. Tree derives one primary parent via
weighted semantic paths, preferring explicit inventory/category membership over
owner→item shortcuts. It uses branching left-to-right subtree spans and elbow
connectors. Cross-links remain in the common model and are available separately
in the selected node's inspector. Topics for routing, registry, GeoIP, archives
and geographic hypotheses are explicitly local presentation groups, with the
member evidence references retained. They are not new source confirmations.

Tree initially shows a preview of the first two levels; collection members are
revealed on demand. Breadcrumbs, search paths, subtree collapse/expand and pinned
dragged positions are retained. Filters do not consume preview slots with hidden
raw model priors. Expansion recalculates the branching layout, rather than
appending unrelated rows of cards.

Graph uses radial thematic sectors and bounded spatial-bin repulsion / relation
constraints, calculated once in a layout worker. It preserves manually adjusted
positions and exposes actual cross-links. It does not run an endless force loop.
The renderer uses Canvas with bounded previews and viewport culling. Default core
is limited to 18 nodes, collection expansion and further batches are explicit;
all original entities/evidence stay saved. A low-zoom node remains a labeled
card, rather than a ten-pixel square. Fit keeps a readable minimum scale; large
expanded collections may require pan/zoom/search.

`semantic_network_v2` view migration preserves the previous encrypted sidecar
bytes as `.layout-v2-backup`. Graph and Tree retain separate positions/viewports;
existing pins survive. No history/evidence database is migrated or reset.

Selected Steam items retain item identifiers, observed float/pattern and quote
fields in bounded agent context. Their own evidence precedes neighbor evidence;
the first targeted follow-up reads that asset with `evidence_get`, rather than
rescraping the whole owner inventory. This does not fabricate a new market quote.

## Paired final-EXE screenshots

| Same saved evidence | Tree | Graph |
| --- | --- | --- |
| Steam: 751 evidence, 748 item rows | [Branching inventory](validation/master-fix-v2/native-graph/actual-steam-v2-tree.png) | [Category network](validation/master-fix-v2/native-graph/actual-steam-v2-graph.png) |
| Network: 10 evidence, IP 87.199.131.94 | [Registry / routing / GeoIP branches](validation/master-fix-v2/native-graph/actual-network-v2-tree.png) | [Relations and registry roles](validation/master-fix-v2/native-graph/actual-network-v2-graph.png) |
| GEOINT: prior saved 10-record control | [Image → hypotheses → candidate](validation/master-fix-v2/native-graph/actual-geoint-tree.png) | [Candidate and actual reference photos](validation/master-fix-v2/native-graph/actual-geoint-graph.png) |

All six screenshots were visually reviewed. Different visible counts are
intentional: Tree hides deeper branches/cross-links by default; neither view
deletes primary data. Steam root now displays the actual current public display
name `battery defuser`; vanity `ohnePixel` is not substituted for it.

## Validation and limits

- 137 frontend tests passed; TypeScript and production UI build passed.
- 52 focused Python tests passed, including encrypted layout backup, semantic
  groups, graph context, selected-asset follow-up and existing Qt graph bridge.
- Source-native controls: 33 checks across Steam/network/GEOINT and synthetic
  1,000-record stress; 11 targeted final GEOINT checks after a preview-filter fix.
  Actual clicks, selection, drag/persistence, group expansion, search and process
  restart were exercised. The worker was active. No provider/inference calls
  were needed for rendering these saved datasets.
- Final frozen EXE: 34 checks passed sequentially on the same four saved
  datasets; all six paired screenshots were inspected. This proves rendering,
  interaction and persistence, not a fresh Steam download or exact geolocation.
- Observed single Canvas paints: Steam 2.6 ms, network 2.0 ms, GEOINT 2.2 ms;
  Tree 2.9 / 1.4 / 5.7 ms. These are individual paint samples on this machine,
  not a measured FPS guarantee or total load time.
- Typed-layout fixtures retain finite coordinates for 1,000 nodes / 5,000 edges;
  native stress verifies aggregation and reversible expansion/search. It does
  not claim all 1,000 labels are simultaneously readable.

Safe metrics, source/synthetic distinctions and screenshot SHA-256 values:
[source controls](validation/master-fix-v2/graph-tree/controls.json),
[final EXE controls](validation/master-fix-v2/native-graph/controls.json).
Earlier QA screenshots found real regressions (hidden groups, fit overlap,
hidden priors consuming preview slots); they are not the accepted artifacts.
GEOINT accuracy/terrain controls have a separate
[benchmark](GEOINT_SOURCES_AND_BENCHMARK.md). Character assets and pet runtime
were untouched.
