from __future__ import annotations

from typing import Optional

from ..models import Release
from .base import Provider

try:
    import musicbrainzngs
    HAVE_MB = True
except ImportError:
    HAVE_MB = False


class MusicBrainzProvider(Provider):
    name = "MusicBrainz"
    logo_url = "https://musicbrainz.org/static/images/favicons/favicon-96x96.png"

    def fetch(self, rel: Release) -> Optional[dict]:
        if not HAVE_MB:
            return None

        musicbrainzngs.set_useragent("archive-flac-uploader", "2.0", "pridefulraisins4@tutamail.com")
        mb_id = None
        try:
            if rel.upc:
                res = musicbrainzngs.search_releases(barcode=rel.upc)
                if res.get("release-list"):
                    mb_id = res["release-list"][0]["id"]
            if not mb_id:
                query = f'artist:"{rel.artist}" AND release:"{rel.title}"'
                res = musicbrainzngs.search_releases(query=query, limit=1)
                if res.get("release-list"):
                    mb_id = res["release-list"][0]["id"]
        except Exception:
            return None

        if not mb_id:
            return None

        print(f"  \u2713 MusicBrainz Match ID: {mb_id}")
        return {"id": mb_id, "url": f"https://musicbrainz.org/release/{mb_id}"}
