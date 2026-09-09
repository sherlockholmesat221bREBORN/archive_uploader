"""MusicBrainz enrichment provider for archive_uploader."""

import urllib.parse
import musicbrainzngs
from typing import Optional, Dict, Any

from archive_uploader import __version__
from archive_uploader.enrichment.base import Provider, BaseEnricher
from archive_uploader.models import ExternalLink, Release


class MusicBrainzProvider(Provider):
    """Enriches release metadata using MusicBrainz API and extracts external relations."""

    name = "musicbrainz"
    logo_url = "https://www.google.com/s2/favicons?domain=musicbrainz.org&sz=32"

    def __init__(self) -> None:
        musicbrainzngs.set_useragent("archive-flac-uploader", __version__, "user@archive.org")

    def fetch(self, rel: Release) -> Optional[Dict[str, Any]]:
        """Fetch metadata dict from MusicBrainz for the pipeline."""
        mb_id = rel.provider_ids.get("musicbrainz")

        try:
            if not mb_id and rel.upc:
                res = musicbrainzngs.search_releases(barcode=rel.upc)
                if res.get("release-list"):
                    mb_id = res["release-list"][0]["id"]

            if not mb_id and rel.artist and rel.title:
                query = f'artist:"{rel.artist}" AND release:"{rel.title}"'
                res = musicbrainzngs.search_releases(query=query, limit=1)
                if res.get("release-list"):
                    mb_id = res["release-list"][0]["id"]

            if not mb_id:
                return None

            mb_url = f"https://musicbrainz.org/release/{mb_id}"
            data: Dict[str, Any] = {
                "id": mb_id,
                "url": mb_url,
            }

            full_mb = musicbrainzngs.get_release_by_id(
                mb_id, includes=["url-rels", "artist-credits", "labels", "recordings"]
            )
            mb_release = full_mb.get("release", {})

            if mb_release.get("title"):
                data["title"] = mb_release["title"]
            if mb_release.get("date"):
                data["date"] = mb_release["date"]
            if mb_release.get("barcode"):
                data["upc"] = mb_release["barcode"]

            if mb_release.get("label-info-list"):
                labels = [
                    l["label"]["name"]
                    for l in mb_release["label-info-list"]
                    if "label" in l and "name" in l["label"]
                ]
                if labels:
                    data["label"] = labels[0]

            return data
        except Exception as e:
            print(f"  ! MusicBrainz fetch failed: {e}")
            return None

    def enrich(self, release: Release) -> Release:
        """Directly enrich a Release object (direct enrichment execution)."""
        fetched = self.fetch(release)
        if not fetched:
            return release

        mb_id = fetched.get("id")
        mb_url = fetched.get("url")

        if mb_id:
            release.provider_ids["musicbrainz"] = mb_id
        if mb_url and not any(link.url == mb_url for link in release.external_links):
            release.external_links.append(
                ExternalLink(service="MusicBrainz", url=mb_url, logo_url=self.logo_url)
            )

        for key in ("title", "date", "upc", "label"):
            if fetched.get(key) and not getattr(release, key, None):
                setattr(release, key, fetched[key])

        return release


# Class name alias for backward compatibility
MusicBrainzEnricher = MusicBrainzProvider
