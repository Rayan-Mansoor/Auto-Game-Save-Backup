import pytest

from saveix.core.providers import ProviderContext, available_providers, load_providers
from saveix.integrations.ludusavi.download import Response
from saveix.integrations.ludusavi.provider import LudusaviProvider


class FakeServer:
    def __init__(self):
        self.body = b"Game: {}\n"
        self.etag = '"v1"'
        self.requests = []

    def __call__(self, url, headers):
        self.requests.append(headers)
        if headers.get("If-None-Match") == self.etag:
            return Response(304, self.etag, b"")
        return Response(200, self.etag, self.body)


def test_downloads_only_when_changed(tmp_path):
    server = FakeServer()
    provider = LudusaviProvider(ProviderContext(tmp_path), fetch=server)

    assert provider.update().startswith("downloaded the latest manifest")
    assert provider.manifest_path.read_bytes() == b"Game: {}\n"
    assert provider.update() == "already up to date"
    assert server.requests[1] == {"If-None-Match": '"v1"'}

    server.body, server.etag = b"Game: {}\nOther: {}\n", '"v2"'
    assert provider.update().startswith("downloaded the latest manifest")
    assert provider.manifest_path.read_bytes().endswith(b"Other: {}\n")
    assert provider.update(force=True).startswith("downloaded the latest manifest")


def test_failed_download_keeps_previous_manifest(tmp_path):
    server = FakeServer()
    provider = LudusaviProvider(ProviderContext(tmp_path), fetch=server)
    provider.update()

    def broken(url, headers):
        return Response(500, None, b"")

    provider.fetch = broken
    with pytest.raises(OSError):
        provider.update(force=True)
    assert provider.manifest_path.read_bytes() == b"Game: {}\n"


def test_registered_as_entry_point(tmp_path):
    assert "ludusavi" in available_providers()
    [provider] = load_providers(["ludusavi"], tmp_path)
    assert provider.name == "ludusavi"
