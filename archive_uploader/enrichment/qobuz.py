from __future__ import annotations

from typing import Optional

from ..models import Release
from .base import Provider

try:
    from kabooz import QobuzSession
    HAVE_QOBUZ = True
except ImportError:
    HAVE_QOBUZ = False

_session = None


def _get_session():
    global _session
    if not HAVE_QOBUZ:
        return None
    if _session is None:
        try:
            _session = QobuzSession.from_config()
        except Exception:
            _session = False
    return _session or None


class QobuzProvider(Provider):
    name = "Qobuz"
    # Swap for whatever badge asset you actually want rendered.
    logo_url = "https://www.qobuz.com/favicon.ico"

    def fetch(self, rel: Release) -> Optional[dict]:
        sess = _get_session()
        if not sess:
            return None

        match = None
        if rel.upc:
            try:
                res = sess.search(rel.upc, search_type="albums", limit=1)
                if res and res.albums.items:
                    match = res.albums.items[0]
                    print(f"  \u2713 Qobuz Barcode Match (UPC: {rel.upc})")
            except Exception:
                pass

        if not match:
            query = f"{rel.artist} {rel.title}".strip()
            try:
                res = sess.search(
                    query, search_type="albums" if rel.kind == "album" else "tracks", limit=1
                )
                items = res.albums.items if rel.kind == "album" else res.tracks.items
                if items:
                    match = items[0]
                    print(f"  \u2713 Qobuz Search Match: {getattr(match, 'display_title', query)}")
            except Exception:
                pass

        if not match:
            return None

        q_id = str(match.id)
        result: dict = {
            "id": q_id,
            "url": f"https://open.qobuz.com/{'album' if rel.kind == 'album' else 'track'}/{q_id}",
        }

        try:
            album_obj = sess.get_album(q_id) if rel.kind == "album" else None
            if album_obj:
                result["genre"] = getattr(getattr(album_obj, "genre", None), "name", "")
                result["label"] = getattr(getattr(album_obj, "label", None), "name", "")
                result["upc"] = getattr(album_obj, "upc", "")
                result["external_description"] = getattr(album_obj, "description", "")
                result["copyright"] = getattr(album_obj, "copyright", "")

                bit_depth = getattr(album_obj, "maximum_bit_depth", None)
                sample_rate = getattr(album_obj, "maximum_sampling_rate", None)
                if bit_depth and sample_rate:
                    result["audio_spec"] = f"{bit_depth}-bit / {sample_rate} kHz"

                if hasattr(album_obj, "image") and getattr(album_obj.image, "large", None):
                    result["cover_url"] = album_obj.image.large
        except Exception as e:
            print(f"  ! Failed fetching Qobuz album details: {e}")

        return result
