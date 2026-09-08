"""
One class per external service. Adding a new provider (Discogs,
Bandcamp, whatever) means writing one file here — payload.py's
description/badge rendering and pipeline.py's merge loop never change,
because they iterate whatever providers are registered.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import Release


class Provider(ABC):
    name: str = "provider"
    logo_url: str = ""

    @abstractmethod
    def fetch(self, rel: Release) -> Optional[dict]:
        """
        Return a dict of fields to merge into the Release. Two keys are
        special and drive the generic badge/external-identifier
        rendering in ia/payload.py:
          - "id":  this service's own id for the release
          - "url": a link to the release's page on that service
        Any other recognized key (genre, label, upc, external_description,
        copyright, audio_spec, cover_url, wikipedia_article) is merged in
        directly. Return None on no match.
        """
        raise NotImplementedError
