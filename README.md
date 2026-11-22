# Hotspot Ledger

A static, noncommercial educational comparison of recent eBird reports at **Iona Beach, British Columbia** and **Hartlen Point, Halifax, Nova Scotia**. Open [Hotspot Ledger](https://coolcode.ca/hotspotledger/).

<!-- coolcode:guide -->
Compare the latest accepted report for each species at the two exact hotspots, then filter to shared species, one coast's feed, or eBird notable species. The daily capture covers the previous 30 days; shorter windows are anchored to that capture date. Species counts are recent-feed counts, not seasonal or historical totals. Missing reports do not establish absence, and observer effort differs. Download the filtered derived CSV or a JSON snapshot; reopening either file happens only in the browser tab.
<!-- /coolcode:guide -->

## Source and interpretation

- [eBird API 2.0 documentation](https://documenter.getpostman.com/view/664302/S1ENwy59), [official data-download guidance](https://support.ebird.org/en/support/solutions/articles/48000838205-download-ebird-data), [hotspot guidance](https://support.ebird.org/en/support/solutions/articles/48001009443).
- The collector resolves the named main hotspots from the official `ref/hotspot/CA-BC` and `ref/hotspot/CA-NS` lists using an explicit accepted-name list and geographic bounds. Ambiguous results stop collection. It saves the returned exact names and location IDs. The Iona Beach label refers to the selected Iona Island/main park hotspot, not a union of every nearby jetty or sewage-pond hotspot. Check its exact name beneath the card.
- For each exact location: `data/obs/{locId}/recent?back=30&cat=species&maxResults=10000&includeProvisional=false&sort=date` and `data/obs/{locId}/recent/notable?back=30&maxResults=10000&detail=simple`.
- Recent observations are the latest report per species, not all checklists. Counts are individual checklist counts and are never summed across reports or snapshots. The notable badge indicates membership in eBird's separate notable feed for the same site/window; it can concern a different checklist than the latest displayed observation. It does not establish a locally rare species or review approval. Notable flags always refer to the full 30-day source capture, including when the visible recent-report window is shortened.
- The source returns only public permitted records. Restricted/sensitive species and missing or uneven reporting limit coverage. Local checklist times are displayed as supplied, while captures use UTC. A 7-day filter means the seven calendar dates ending on the saved capture's UTC date; local date boundaries can differ from the original API rolling window.
- Example: a species returned at Iona but not Hartlen is **only in Iona's recent feed**, not absent from Nova Scotia. A count of 12 means 12 on that displayed checklist, not 12 birds across the period.
- Seasonal and lifetime totals are intentionally not inferred; follow the direct eBird hotspot links for eBird's historical/seasonal products.

## Credential, collection, snapshots

Set repository **Actions secret `EBIRD_API_KEY`**. A personal eBird account/API key is required. Keys are read only as environment variables by Python; never paste one into the website or commit one. They are sent in the `X-eBirdApiToken` request header, not in URLs or saved source metadata.

```sh
python3 scripts/collect.py  # EBIRD_API_KEY supplied in environment
python3 scripts/build.py    # offline, uses saved data only
```

The daily workflow runs at **10:23 UTC** (`23 10 * * *`). It collects on schedules/manual dispatch and on first main push if the saved status is not ready. Pull requests never use the key. If the first run has no key, it may publish only the explicit awaiting-source state and local file workflow. A missing key after a successful capture fails the refresh and preserves the last deployment; an invalid key or any source error also fails. Six bounded requests per capture, at least 1.1 seconds apart; no numeric public quota was verified in the primary documentation. HTTP 429 honors a numeric Retry-After up to 60 seconds; larger waits abort until a later run. Requests have 45-second timeouts, at most three attempts, and an 8 MB response cap. An observation response reaching the 10,000-row cap fails rather than silently truncating coverage. Failed collection/tests/build prevent deployment and preserve the last published capture.

`data/current.json` contains derived species comparisons, exact hotspot metadata, endpoint URLs, response hashes, and captured time. Original API responses, observer identities and media are not persisted. `archive/*.json` stores immutable derived snapshots; `data/history.json` lists their SHA-256 hashes; `data/index.json` provides small coverage/freshness metadata for the CoolCode hub. Overlapping snapshots must not be added together as new sightings. The default empty state is explicitly `awaiting_source` and contains no invented records. An empty but successful source feed is valid and different from unavailable data.

GitHub schedules may be delayed and may stop for inactive public repositories. Check the displayed capture date. The site flags captures older than two days.

## Local files and privacy

JSON snapshots and derived CSV exports can be opened locally (maximum 5 MB, 2,000 species). Files remain in tab memory and are never uploaded or retained. Untrusted names render as text; checklist links must use the eBird checklist domain/path. Local files are explicitly labelled as unverified local provenance. Exports retain source attribution and the applicable data terms. No API requests occur in the browser. The only routine external script is CoolCode's aggregate visit counter; eBird pages open when their links are selected. No media are downloaded or redistributed.

## Attribution and reuse

Derived from **eBird.org, Cornell Lab of Ornithology, and its contributors**. This independent project is not endorsed by Cornell; no Cornell/eBird logos are used. All derived datasets, including CSV exports and archives, remain subject to the [eBird Data Access Terms of Use](https://www.birds.cornell.edu/home/ebird-data-access-terms-of-use/) and [eBird API Terms of Use](https://www.birds.cornell.edu/home/ebird-api-terms-of-use/). Noncommercial research and education only; commercial use requires Cornell's written permission. Do not redistribute original API-format data. The data terms require an electronic copy of published products to be supplied to eBird; the publisher should send the public product link through the contact specified in those terms. The app does not send messages on your behalf. Media licensing is separate; this app uses no eBird images, audio or video.

## Development and verification

```sh
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
python3 -m http.server 8000 --directory dist
```

CI installs Playwright solely for acceptance tests at the project subpath, covering JSON/CSV import, filters, safe rendering, downloads, restore, and mobile layout. Browser fixtures are explicitly synthetic test inputs; they are not part of the published dataset. Build code is Python standard library; the app uses no runtime dependencies. Keep all assets relative. Do not commit `dist/` or set a CNAME.
