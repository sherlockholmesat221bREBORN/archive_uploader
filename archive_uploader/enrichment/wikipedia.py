from __future__ import annotations

import urllib.parse
from typing import Optional

import requests

from ..models import Release
from .base import Provider


class WikipediaProvider(Provider):
    name = "Wikipedia"
    logo_url = "https://en.wikipedia.org/static/favicon/wikipedia.ico"

    def fetch(self, rel: Release) -> Optional[dict]:
        if not rel.artist or not rel.title:
            return None

        headers = {"User-Agent": "ArchiveUploader/2.0 (https://archive.org)"}
        search_queries = [
            f'"{rel.title}" "{rel.artist}" album',
            f'"{rel.title}" {rel.artist}',
            f'"{rel.title}" soundtrack',
        ]

        for query in search_queries:
            try:
                search_url = "https://en.wikipedia.org/w/api.php"
                params = {"action": "query", "list": "search", "srsearch": query, "format": "json"}
                res = requests.get(search_url, params=params, headers=headers, timeout=5)
                if res.status_code != 200:
                    continue

                results = res.json().get("query", {}).get("search", [])
                if not results:
                    continue

                page_title = results[0]["title"]
                summary_url = (
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/"
                    f"{urllib.parse.quote(page_title)}"
                )
                s_res = requests.get(summary_url, headers=headers, timeout=5)
                if s_res.status_code == 200:
                    data = s_res.json()
                    extract = data.get("extract", "")
                    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

                    if extract and len(extract) > 100 and "disambiguation" not in data.get("type", ""):
                        print("  \u2713 Retrieved Wikipedia background article")
                        return {
                            "url": page_url,
                            "wikipedia_article": (
                                f"{extract}<br><br><i>Read more on "
                                f"<a href='{page_url}' target='_blank'>Wikipedia Article</a></i>"
                            ),
                        }
            except Exception:
                pass

        return None
