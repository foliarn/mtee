"""The marketplace list of the Plugins view model: sources, keys, duplicates, failures.

It uses the helpers of ``test_plugins_view_model``: the temporary data folder, the fake job service
and the fake opener. No test reaches the internet.
"""

from __future__ import annotations

import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_plugins_view_model import (
    FakeManager,
    FakeOpener,
    Harness,
    _entry,
    _index,
    _index_url,
    _install_on_disk,
    _package,
    _row,
)

from mtee.plugins import marketplace
from mtee.plugins.installer import plugins_folder

OFFICIAL = marketplace.OFFICIAL_ADDRESS
OWNER = "owner/repo"
OWNER_INDEX = "https://raw.githubusercontent.com/owner/repo/HEAD/index.json"
OWNER_PACKAGE = "https://github.com/owner/repo/releases/download/alpha-1.0.0/alpha-1.0.0.mteeplugin"
OFFICIAL_PACKAGE = (
    "https://github.com/foliarn/mtee-plugins/releases/download/alpha-1.0.0/alpha-1.0.0.mteeplugin"
)


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    harness = Harness(tmp_path)
    yield harness
    harness.close()


class SourcesOpener(FakeOpener):
    """Like ``FakeOpener``; an address listed in ``failures`` fails with its error."""

    def __init__(self, answers: dict[str, bytes], failures: dict[str, BaseException]) -> None:
        super().__init__(answers)
        self.failures = failures

    def __call__(self, request: Any, timeout: float = 0) -> Any:
        if request.full_url in self.failures:
            self.urls.append(request.full_url)
            raise self.failures[request.full_url]
        return super().__call__(request, timeout=timeout)


def _at(package: Path, url: str, version: str = "1.0.0") -> dict[str, Any]:
    """The entry of ``package`` with the download address ``url``."""
    entry = _entry(package, "alpha", version)
    entry["versions"][0]["url"] = url
    return entry


def _two_sources(package: Path) -> dict[str, bytes]:
    """The official list and the owner's list, each offering ``alpha`` with the same package."""
    return {
        _index_url(): _index([_at(package, OFFICIAL_PACKAGE)]),
        OWNER_INDEX: _index([_at(package, OWNER_PACKAGE)]),
        OFFICIAL_PACKAGE: package.read_bytes(),
        OWNER_PACKAGE: package.read_bytes(),
    }


def test_addresses_are_normalized_and_read_from_their_index_url() -> None:
    assert marketplace.normalize_address(" owner/repo ") == OWNER
    assert marketplace.normalize_address("https://github.com/owner/repo/") == OWNER
    list_url = "https://example.org/list/index.json"
    assert marketplace.normalize_address(list_url) == list_url
    with pytest.raises(marketplace.MarketplaceError) as caught:
        marketplace.normalize_address("not a marketplace")
    assert str(caught.value) == (
        "Enter a GitHub repository as owner/repo, or an https address of an index.json."
    )
    assert marketplace.index_url(OWNER) == OWNER_INDEX
    assert marketplace.index_url(OFFICIAL) == marketplace.INDEX_URL
    assert marketplace.index_url(list_url) == list_url


def test_the_official_marketplace_is_the_only_one_by_default(harness: Harness) -> None:
    view = harness.start()

    assert view.property("marketplaces") == [
        {
            "address": OFFICIAL,
            "title": OFFICIAL,
            "official": True,
            "enabled": True,
            "stateText": "",
        }
    ]
    assert view.property("marketplaceAddError") == ""


def test_a_broken_stored_list_falls_back_to_the_official_marketplace(harness: Harness) -> None:
    harness.settings.set("plugins.marketplaces", "not a list")
    view = harness.start()

    assert [item["address"] for item in view.property("marketplaces")] == [OFFICIAL]


def test_added_marketplaces_are_saved_and_can_be_switched_off_and_removed(
    harness: Harness,
) -> None:
    view = harness.start()

    assert view.addMarketplace("https://github.com/owner/repo") is True

    assert harness.settings.get_json("plugins.marketplaces") == [
        {"address": OFFICIAL, "enabled": True},
        {"address": OWNER, "enabled": True},
    ]
    again = harness.view(FakeManager([]))
    listed = again.property("marketplaces")
    assert [item["address"] for item in listed] == [OFFICIAL, OWNER]
    assert listed[1]["title"] == OWNER and listed[1]["official"] is False

    again.setMarketplaceEnabled(OWNER, False)
    assert harness.settings.get_json("plugins.marketplaces")[1]["enabled"] is False
    assert harness.view(FakeManager([])).property("marketplaces")[1]["enabled"] is False

    again.removeMarketplace(OWNER)
    assert harness.settings.get_json("plugins.marketplaces") == [
        {"address": OFFICIAL, "enabled": True}
    ]
    assert [item["address"] for item in harness.view(FakeManager([])).property("marketplaces")] == [
        OFFICIAL
    ]


def test_the_official_marketplace_is_first_and_cannot_be_removed(harness: Harness) -> None:
    harness.settings.set_json("plugins.marketplaces", [{"address": OWNER, "enabled": True}])
    view = harness.start()

    assert [item["address"] for item in view.property("marketplaces")] == [OFFICIAL, OWNER]
    assert view.property("marketplaces")[0]["official"] is True

    view.removeMarketplace(OFFICIAL)

    assert [item["address"] for item in view.property("marketplaces")] == [OFFICIAL, OWNER]


def test_a_refused_address_keeps_its_reason_until_it_is_cleared(harness: Harness) -> None:
    view = harness.start()

    assert view.addMarketplace("https://github.com/foliarn/mtee-plugins") is False
    assert view.property("marketplaceAddError") == "This marketplace is already in the list."
    assert view.addMarketplace("nonsense") is False
    assert view.property("marketplaceAddError") == (
        "Enter a GitHub repository as owner/repo, or an https address of an index.json."
    )
    view.clearMarketplaceAddError()

    assert view.property("marketplaceAddError") == ""
    assert len(view.property("marketplaces")) == 1


def test_two_sources_offering_one_id_give_two_rows_with_distinct_keys(
    harness: Harness,
) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    harness.opener = FakeOpener(_two_sources(package))
    view = harness.start()
    assert view.addMarketplace(OWNER) is True
    view.checkMarketplace()

    rows = view.property("marketplace")
    assert [row["key"] for row in rows] == [f"alpha@{OFFICIAL}", f"alpha@{OWNER}"]
    assert [row["source"] for row in rows] == [OFFICIAL, OWNER]
    assert [row["sourceTitle"] for row in rows] == ["Official", OWNER]
    assert all(row["id"] == "alpha" and row["duplicate"] is True for row in rows)
    assert [item["stateText"] for item in view.property("marketplaces")] == [
        "1 plugin",
        "1 plugin",
    ]
    assert view.detail("alpha")["key"] == f"alpha@{OFFICIAL}"
    assert view.detail(f"alpha@{OWNER}")["source"] == OWNER
    assert view.detail(f"alpha@{OWNER}")["state"] == "install"
    assert view.detail("alpha@missing.example") == {}


def test_install_by_key_downloads_from_the_source_of_that_key(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    harness.opener = FakeOpener(_two_sources(package))
    view = harness.start()
    view.addMarketplace(OWNER)
    view.checkMarketplace()

    view.install(f"alpha@{OWNER}")

    assert OWNER_PACKAGE in harness.opener.urls
    assert OFFICIAL_PACKAGE not in harness.opener.urls
    pending = view.property("pendingInstall")
    assert pending["source"] == "marketplace" and pending["sourceAddress"] == OWNER
    assert pending["sourceText"] == f"Downloaded from {OWNER}. Its file matched the list."
    view.confirmInstall()

    alpha = _row(view.property("installed"), "alpha")
    assert alpha["installedFrom"] == "marketplace"
    assert alpha["offerKey"] == f"alpha@{OWNER}"
    assert harness.settings.get("plugin-source-address.alpha") == OWNER
    assert list((plugins_folder(harness.data_dir) / ".downloads").iterdir()) == []
    # The key of the source it came from gives the installed row; the other key gives its own row.
    assert view.detail(f"alpha@{OWNER}")["offerKey"] == f"alpha@{OWNER}"
    assert view.detail("alpha")["offerKey"] == f"alpha@{OWNER}"
    official_row = view.detail(f"alpha@{OFFICIAL}")
    assert official_row["source"] == OFFICIAL and official_row["state"] == "installed"


def test_the_official_pending_install_names_the_official_list(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    harness.opener = FakeOpener(_two_sources(package))
    view = harness.start()
    view.checkMarketplace()

    view.install("alpha")

    pending = view.property("pendingInstall")
    assert pending["sourceAddress"] == OFFICIAL
    assert pending["sourceText"] == (
        "Downloaded from the official MTEE plugin list. Its file matched the list."
    )
    assert OFFICIAL_PACKAGE in harness.opener.urls


def test_an_update_is_offered_only_from_the_source_the_plugin_came_from(
    harness: Harness,
) -> None:
    _install_on_disk(harness, _package(harness.tmp / "old", "alpha", "1.0.0"))
    harness.settings.set("plugin-source.alpha", "marketplace")
    harness.settings.set("plugin-source-address.alpha", OWNER)
    newer = _package(harness.tmp / "new", "alpha", "1.1.0")
    harness.opener = FakeOpener(
        {
            _index_url(): _index([_at(newer, OFFICIAL_PACKAGE, "1.1.0")]),
            OWNER_INDEX: _index([_at(_package(harness.tmp / "same", "alpha"), OWNER_PACKAGE)]),
        }
    )
    view = harness.start()
    view.addMarketplace(OWNER)
    view.checkMarketplace()

    alpha = _row(view.property("installed"), "alpha")
    assert alpha["offerKey"] == f"alpha@{OWNER}"
    assert alpha["updateVersion"] == ""
    official_row = view.detail(f"alpha@{OFFICIAL}")
    assert official_row["state"] == "installed" and official_row["version"] == "1.0.0"


def test_an_old_marketplace_install_without_an_address_comes_from_the_official_list(
    harness: Harness,
) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    _install_on_disk(harness, package)
    harness.settings.set("plugin-source.alpha", "marketplace")
    harness.opener = FakeOpener({_index_url(): _index([_at(package, OFFICIAL_PACKAGE)])})
    view = harness.start()
    view.marketplaceRequested()

    alpha = _row(view.property("installed"), "alpha")
    assert alpha["installedFrom"] == "marketplace"
    assert alpha["offerKey"] == f"alpha@{OFFICIAL}"


def test_a_failed_list_is_one_sentence_and_the_other_lists_still_load(
    harness: Harness,
) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    error = urllib.error.URLError("offline")
    harness.opener = SourcesOpener(
        {_index_url(): _index([_at(package, OFFICIAL_PACKAGE)])},
        failures={OWNER_INDEX: error},
    )
    view = harness.start()
    view.addMarketplace(OWNER)

    view.checkMarketplace()

    assert view.property("marketplaceState") == "ready"
    assert view.property("marketplaceError") == (
        "1 of 2 plugin lists could not be read. See Settings > Plugins."
    )
    listed = view.property("marketplaces")
    assert listed[0]["stateText"] == "1 plugin"
    assert listed[1]["stateText"] == "The plugin list could not be read: the connection failed."
    assert [row["key"] for row in view.property("marketplace")] == [f"alpha@{OFFICIAL}"]
    assert harness.jobs.failures == []


def test_the_read_fails_only_when_every_list_failed(harness: Harness) -> None:
    error = urllib.error.URLError("offline")
    harness.opener = SourcesOpener({}, failures={_index_url(): error, OWNER_INDEX: error})
    view = harness.start()
    view.addMarketplace(OWNER)

    view.checkMarketplace()

    assert view.property("marketplaceState") == "failed"
    assert view.property("marketplaceError") == (
        "The plugin list could not be read: the connection failed."
    )
    assert [item["stateText"] for item in view.property("marketplaces")] == [
        "The plugin list could not be read: the connection failed.",
        "The plugin list could not be read: the connection failed.",
    ]
    assert len(harness.jobs.failures) == 1


def test_changing_the_list_after_a_read_reads_the_lists_again(harness: Harness) -> None:
    package = _package(harness.tmp / "pkg", "alpha")
    harness.opener = FakeOpener(_two_sources(package))
    view = harness.start()
    view.marketplaceRequested()
    assert harness.opener.urls == [_index_url()]

    view.addMarketplace(OWNER)
    assert harness.opener.urls[-1] == OWNER_INDEX
    assert len(view.property("marketplace")) == 2

    view.setMarketplaceEnabled(OWNER, False)
    assert [row["source"] for row in view.property("marketplace")] == [OFFICIAL]
    assert view.property("marketplaces")[1]["stateText"] == ""

    view.setMarketplaceEnabled(OWNER, True)
    assert len(view.property("marketplace")) == 2

    view.removeMarketplace(OWNER)
    assert [row["source"] for row in view.property("marketplace")] == [OFFICIAL]
    assert [item["address"] for item in view.property("marketplaces")] == [OFFICIAL]
