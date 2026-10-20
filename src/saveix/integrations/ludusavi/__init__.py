"""Provider backed by the Ludusavi manifest (https://github.com/mtkennerly/ludusavi-manifest).

The manifest is a community database compiled from PCGamingWiki, published under the
MIT license. It is downloaded on request and cached in the provider's data folder.
"""

from __future__ import annotations

from saveix.core.providers import ProviderContext
from saveix.integrations.ludusavi.provider import LudusaviProvider


def create(context: ProviderContext) -> LudusaviProvider:
    return LudusaviProvider(context)
