# Network / GeoIP — Master Fix V2

Source/live validation: 2026-11-02. Final V2 EXE validation remains pending.

## Sources and limits

`network_geoip` queries two independent HTTPS endpoints for the explicit public
IP, without account keys or caller-IP discovery. Registration country is kept
separate. [ipwhois documentation](https://ipwhois.io/documentation) permits
anonymous/commercial use, 1,000 requests per client IP/day, no SLA.
[ipapi.is anonymous tier](https://ipapi.is/free-tier.html) permits 30 lookups per
client IP/UTC day and returns fewer fields than its keyed API. It explicitly
requires respecting 429; repeated requests after exhaustion can cause a ban.
Both providers are queried within their published limits; 24-hour cache and
403/429 backoff avoid repeated quota failures. Cache retains original observation
time, not a new observation. No accuracy radius or database-record update date
was supplied, so these fields remain null. No VPN/security verdict is inferred.

## Live observations

- `66.249.67.41`: both sources returned United States / California, but ipwhois
  reported San Jose and ipapi.is Mountain View. The report preserves the city
  disagreement and both actual source URLs. Coordinates are database estimates,
  not a verified physical device/person position.
- `87.199.131.94`: both sources reported Kazakhstan / Almaty. The two coordinates
  agree at the displayed two-decimal precision; their original values remain in
  evidence. This agreement does not establish a user's location.
- RDAP `31.0.0.0/16`: live response matched that exact /16. A separate
  `31.1.0.0/16` control returned the larger non-CIDR interval
  31.1.0.0–31.2.127.255, represented as `31.1.0.0/16` plus `31.2.0.0/17` and
  explicitly qualified as a parent response. Historical /8 mismatch is covered
  by a fixture; the current live response did not reproduce /8.
- RDAP `87.199.131.94`: returned containing range `87.199.128.0/22`. Explicit
  vCard kind/org identifies an organization. Maintainer handles and RIPE NCC
  remain separate registry types, without attributing the service operator.

`А какая локация?` after the scoped target `87.199.131.94` ran the actual agent:
seven network operations, ten evidence records, seven DeepSeek HTTP 200
responses, 57.069 seconds, completed with no provider error. This control used
an isolated QA profile, no user history and no personal source keys.

## Semantics and tests

RDAP range matching uses actual start/end addresses, including IPv6 and
non-CIDR intervals. Parent, exact, subrange and overlap are distinct; mismatched
new source responses are rejected. BGP facts are canonicalized and deduplicated
with all distinct source/time references; different values are retained.
The graph has separate registry range, maintainer/contact and approximate GeoIP
nodes. Registration ranges are not labeled BGP announcements.

88 focused Python tests passed (`network-final-stage-gate.log`), covering range
matching, registry roles, malformed schemas, BGP provenance, independent-source
failure and short contextual routing. Frontend TypeScript passed. Fixtures are
not counted as live source observations. Safe live metadata is in
`validation/master-fix-v2/network-controls.json`; raw controlled receipts remain
in ignored QA output. Full final EXE checks will be reported separately.
