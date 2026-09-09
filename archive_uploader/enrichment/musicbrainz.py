"""MusicBrainz enrichment provider for archive_uploader."""

import urllib.parse
import musicbrainzngs

from archive_uploader import __version__
from archive_uploader.enrichment.base import BaseEnricher
from archive_uploader.models import ExternalLink, Release


class MusicBrainzEnricher(BaseEnricher):
    """Enriches release metadata using MusicBrainz API and extracts external relations."""

    def __init__(self) -> None:
        musicbrainzngs.set_useragent("archive-flac-uploader", __version__, "user@archive.org")

    def enrich(self, release: Release) -> Release:
        try:
            mb_id = None
            if release.upc:
                res = musicbrainzngs.search_releases(barcode=release.upc)
                if res.get("release-list"):
                    mb_id = res["release-list"][0]["id"]

            if not mb_id and release.artist and release.title:
                query = f'artist:"{release.artist}" AND release:"{release.title}"'
                res = musicbrainzngs.search_releases(query=query, limit=1)
                if res.get("release-list"):
                    mb_id = res["release-list"][0]["id"]

            if mb_id:
                release.provider_ids["musicbrainz"] = mb_id
                mb_url = f"https://musicbrainz.org/release/{mb_id}"
                
                # Add MusicBrainz link badge
                if not any(link.url == mb_url for link in release.external_links):
                    logo = "https://www.google.com/s2/favicons?domain=musicbrainz.org&sz=32"
                    release.external_links.append(
                        ExternalLink(service="MusicBrainz", url=mb_url, logo_url=logo)
                    )

                try:
                    full_mb = musicbrainzngs.get_release_by_id(mb_id, includes=["url-rels"])
                    mb_release = full_mb.get("release", {})

                    relations = mb_release.get(
                        "url-relation-list",
                        mb_release.get("relation-list", mb_release.get("relations", [])),
                    )
                    for url_rel in relations:
                        target_url = ""
                        if isinstance(url_rel, dict):
                            target_url = url_rel.get("target", "")
                            if not target_url and isinstance(url_rel.get("url"), dict):
                                target_url = url_rel.get("url", {}).get("resource", "")

                        if not target_url:
                            continue

                        domain = urllib.parse.urlparse(target_url).netloc.replace("www.", "")
                        logo = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"

                        if "spotify.com/album/" in target_url:
                            service = "Spotify"
                            spot_id = target_url.split("/album/")[-1].split("?")[0]
                            release.provider_ids["spotify"] = spot_id
                        elif "discogs.com/release/" in target_url:
                            service = "Discogs"
                            disc_id = target_url.split("/release/")[-1].split("-")[0]
                            release.provider_ids["discogs"] = disc_id
                        elif "apple.com" in target_url and "/id" in target_url:
                            service = "Apple Music"
                            app_id = target_url.split("/id")[-1].split("?")[0]
                            release.provider_ids["apple_music"] = app_id
                        else:
                            service = domain.capitalize()

                        if not any(link.url == target_url for link in release.external_links):
                            release.external_links.append(
                                ExternalLink(service=service, url=target_url, logo_url=logo)
                            )

                except Exception as e:
                    print(f"  ! Warning: Failed to fetch MB url-rels: {e}")

        except Exception as e:
            print(f"  ! MusicBrainz search failed: {e}")

        return release
