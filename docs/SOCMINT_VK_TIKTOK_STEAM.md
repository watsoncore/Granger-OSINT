# Public SOCMINT — Master Fix V2

Work in progress. These results concern source/live checks, not the final V2 EXE.
Final native acceptance and the distinct Tree/Graph redesign remain outstanding.

## VK

`vk_public` now has a key-free public path; the existing token adapter is retained
as optional `vk_authorized` with approval. The new target normalizer handles
vk.com/vk.ru/mobile aliases, numeric profiles, screen names, club/public and
wall posts. Canonical arguments deduplicate alias requests. URL-derived IDs
are explicitly distinguished from independent identity verification.

The collector accepts specific OG title/image/description and actual visible
post links. A generic title, login page, challenge or empty JS shell is not a
profile. If direct HTTP reports an unsupported browser, it tries the genuine
installed Edge once, retaining the application identifier and all network
restrictions. It never retries a login or CAPTCHA.

2026-11-02 controls: vk.com/apiclub and vk.com/vk returned HTTP redirects to
mobile public URLs and HTTP 200 with “Ваш браузер устарел”. This was initially
misclassified as login and corrected. Browser robots fetching then exposed TLS
verify code 19. The worker now uses the same integrity-checked certifi CA bundle
as the main pinned HTTP transport, with certificate and hostname verification
enabled. No runtimes, CA stores or Windows settings were changed.

After that fix Edge navigated successfully, but returned a generic VK title,
zero-width loading placeholders, no metadata and no profile fields after a
bounded six-second content wait. The exact scope is **unconfirmed public
content/JS shell**, not “VK globally unavailable” and not proof of privacy.

An independent CDX request found two apiclub snapshots, dated 2011-07-13 and
2011-08-22. Both actual snapshot contents were read and classified login_form;
neither is claimed as profile evidence. The public-source search fallback was
empty and explicitly reports its limited HN/Wikipedia/OpenLibrary coverage;
it is not a general Google index. No private-profile success is claimed.

## TikTok

The general [TikTok terms](https://www.tiktok.com/legal/page/row/terms-of-service/en)
restrict automated collection from the site. The documented
[creator-profile oEmbed API](https://developers.tiktok.com/docs/en/embed-creator-profiles)
provides a permitted public integration without an account key. The new
`tiktok_public_profile` uses that API rather than reverse-engineered signatures,
cookies, private endpoints or unrestricted page scraping.

Actual controls @scout2015 and its documented video
6718335390845095173 each received HTTP 200. The profile returned author_name,
author_url, uniqueId from the returned embed markup and embed metadata. The
video returned its embed type/product ID. Returned HTML is parsed but never
executed in the application renderer. Video IDs remain separate from user IDs
and account creation. The original local tiktok_timestamp is unchanged.

The observed response did **not** provide avatar, full counters, userId, secUid,
region, language, verified or account creation. These remain null, never zero
or guessed dates. Full fields would require an appropriately authorized source
such as TikTok Research/Display API; that is not a key-free baseline capability.
Source cards show a field table and visible JSON, including missing-field
qualification. Cache TTL is five minutes; rate-limit errors retain backoff.
The ordinary command “Проверь TikTok @scout2015.” was also exercised through the
real AgentRunner and gateway: one partial profile call, one evidence_get, three
HTTP 200 model responses, one retained evidence record, 23.837 s. This exposed
and fixed sentence-final punctuation being appended to an inferred username.

## Checks and remaining work

206 source/browser/registry fixtures passed; 33 focused frontend tests and
TypeScript checking passed.
Additional routing fixtures cover natural “TikTok @name” and scoped counters
follow-ups. Fixtures are distinct from the live controls above.

After the browser changes a real permitted practice-site flow completed input,
submit, next-page click, DOM/table (25 rows), screenshot and local OCR. Cancel
took 1.146 s and left zero owned processes. Process-tree RSS during that flow
was 733,224,960 bytes (13 processes); this is a sample, not a general peak bound.

## Steam inventory

`steam_inventory` is a separate typed capability over the public Community JSON
response, not a claim that Steam's keyed Web API is anonymously available.
It runs in the existing disposable process with bounded pages, bytes, memory,
time, rate and cancellation; uses no account, cookies, trades or inspect execution;
checks robots and pinned public DNS/TLS. Steam's
[terms](https://store.steampowered.com/agreement/?l=english) and
[API terms](https://steamcommunity.com/dev/apiterms) were reviewed. This is a
user-requested passive read, with no account/gameplay/market action automation.
The Community endpoint is subject to change and access restrictions.

Actual 2026-11-02 control 76561198045277210 resolved XML customURL ohnePixel and
display name battery defuser; these fields are not a real-world identity claim.
Inventory JSON returned actual assets/descriptions/asset_properties. A full
cursor walk retained **748 unique asset IDs**, all with names, while the source
reported **795**. Pagination ended before that count. A second walk with a
different page size produced the same 748. Coverage is therefore **partial**;
no 47 missing records are invented and no claim of full inventory is made.

504 retained items had source-provided Wear Rating and Pattern Template.
No sticker or rare-pattern valuation was inferred. Actual Market quotes covered
four items (three distinct names); observed subtotal 0.22 USD, with 744 items
unpriced. That is explicitly not total inventory value. Quote time/currency,
item IDs, tags, exterior, source endpoint, page cursors and body receipts are
retained. Unknown prices are not zero. Errors/429 stop requests and preserve
already received items; backoff prevents a new worker during cooldown.

Two actual 256×256 item images and the actual 184×184 avatar were downloaded,
format-verified and cached via MediaStore, with source URL/date/SHA. Renderer
loads only backend-produced data images. Source art is not regenerated.

Live testing found and fixed a second data-loss boundary: the generic registry
kept only 20 results. Inventory now preserves the entire bounded item payload;
regressions check 257 rows through registry, AgentRunner and checkpoint. A
1000-item projection test retains all item nodes while passing a compact model
summary. The real 748-item projection retained 748 item nodes (777 entities,
3016 relations), taking 1.055 s; model context was 6852 characters rather than
the initial 126609-character profile/source duplication.

The existing overview now includes a virtual table and real-image gallery with
game/category/name/rarity filters, unknown-field qualifications and item-to-graph
selection. Graph nodes distinguish game inventory, category and item; ownership
is a public account observation, never a person attribution. API page references
are shared rather than producing a separate page node for every item. Final
native appearance/interaction testing is still required.

The short natural command was exercised through the real gateway and runner:
751 evidence records, seven HTTP 200 model responses, no provider error. Current
cursor enums constrain the next page and exhausted scopes retire that binding;
one model-proposed repeat was skipped without a network request. The bounded
run completed in 90.222 s. Source failures and item coverage remain distinct from
the model's completed report status.

Stage checks: 160 Python fixtures, 13 focused frontend tests, TypeScript passed;
37 focused cursor/agent fixtures passed separately. A new run clears the
registry's old URL/frontier working projection, retaining only explicitly
selected immutable image observations for CPU reuse. Journals/vault are intact.

Receipts are in the Master Fix V2 validation directory; raw controlled pages and
inventories stay in ignored output. Pending: richer authorized TikTok fields
when available, remaining network/GEOINT/layout work and final EXE/native matrix.
