# Decisions

One paragraph each on the things in this codebase that look removable
but aren't. Read this before touching any of the files it references.

## Legacy identifier fallback (`ia/identifiers.py`)

Two identifier schemes have existed over time: an untruncated slug, and
a version truncated to 50 characters. `resolve_identifier` checks IA
for the legacy id before minting a new one. Removing this "because it
looks redundant" causes old items to get re-uploaded under a new
identifier instead of resumed — a duplicate, not a fix.

## Root-FLAC repair mode (`ia/uploader.py`)

If a multi-disc release was previously uploaded flat (before this
logic existed, or from a bug) and is now being uploaded with proper
`CD 01/`, `CD 02/` subpaths, `upload_release` detects and purges the
old root-level files before re-uploading. Without this, IA ends up
with both the old flat files and the new nested ones for the same
release.

## Append-only per-device state log, not a shared SQLite file
(`state/log_store.py`)

Multiple devices, no server, sometimes different networks. A single
SQLite file synced between devices (Syncthing or similar) can corrupt
or fork on genuinely concurrent writes. Each device instead only ever
appends to its own `<device_id>.ndjson` — the sync layer just has to
move files around, never merge their contents, so there's no
concurrent-write hazard regardless of timing.

This state store is also **only ever a cache**. `ia/uploader.py`
always re-checks the live IA file manifest before skipping an upload —
that live check is the actual correctness guarantee. If the local
state is stale, wrong, or missing entirely, the worst case is a
redundant API call, never a missed or duplicated upload. Don't remove
the live check to "avoid an extra request."

## Metadata merge order: tags -> providers -> overrides
(`enrichment/pipeline.py`, `enrichment/overrides.py`)

Overrides in `.archive_meta.json` are applied last, always, even when
nothing changed in enrichment. This is deliberate: it's what lets a
rare item with no online match use the exact same mechanism as
"editing a value a provider got wrong," and it's what guarantees
re-running enrichment can never silently overwrite a hand-edited
field.

## Provider-agnostic badges/identifiers, not per-service ifs
(`ia/payload.py`)

`_render_link_badges` and the `external-identifier` / `<name>_id`
metadata fields loop over whatever's in `rel.external_links` /
`rel.provider_ids`. Adding Discogs or Bandcamp means writing one
`enrichment/<service>.py` file — it should never require editing
`payload.py`. If a change to add a provider touches `payload.py`,
that's a sign the change went in the wrong file.

## 128 kbps Opus specifically (`packaging.py`)

Chosen as "good enough to listen to, small enough to ship as a
convenience download alongside the lossless FLAC." Not a default
worth "optimizing" without being asked — it's a taste decision, not a
technical one.
