"""build_feed_for_series のエンドツーエンド（HTTP モック）テスト。"""

from pathlib import Path

import pytest
import requests_mock as rm_module

import main


SERIES_HASH = "5611422227f8d"
SERIES_URL = main.SERIES_URL_TEMPLATE.format(series_hash=SERIES_HASH)
FIXTURES = Path(__file__).parent / "fixtures"


def _series_html(
    title: str = "テスト作品",
    cover: str = "https://example.com/cover.jpg",
    episodes: list[dict[str, str]] | None = None,
) -> str:
    episode_blocks: list[str] = []
    for ep in episodes or []:
        paid = ep.get("paid")
        paid_html = (
            '<div class="series-eplist-item-access-paid">'
            '<img src="/images/icons/coin.svg" alt="コイン" /></div>'
            if paid
            else ""
        )
        waitfree = ep.get("waitfree")
        waitfree_html = (
            '<svg class="series-eplist-item-access-icon" data-e2e="eliWfIcon"></svg>'
            if waitfree
            else ""
        )
        episode_blocks.append(
            f'<a class="series-eplist-item-link" href="/episodes/{ep["hash"]}">'
            f'<span class="series-eplist-item-h-text">{ep["title"]}</span>'
            f'<div class="series-eplist-item-meta-date">{ep["date"]}</div>'
            f"{paid_html}"
            f"{waitfree_html}"
            "</a>"
        )
    episodes_html = "".join(episode_blocks)
    return (
        "<!doctype html><html><body>"
        f'<h1 class="series-h-title"><span class="g-hidden">ビッコミの</span>{title}</h1>'
        f'<img class="series-cover-image" src="{cover}" />'
        f"{episodes_html}"
        "</body></html>"
    )


@pytest.fixture
def feeds_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(main, "FEEDS_DIR", tmp_path)
    return tmp_path


def test_filters_paid_episodes(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    html = _series_html(
        title="らーめん再遊記",
        episodes=[
            {"hash": "aaa111", "title": "第1杯", "date": "2024/01/01"},
            {"hash": "bbb222", "title": "第2杯", "date": "2024/01/15", "paid": "y"},
            {"hash": "ccc333", "title": "第3杯", "date": "2024/02/01"},
        ],
    )
    requests_mock.get(SERIES_URL, text=html)

    result = main.build_feed_for_series(main.create_session(), SERIES_HASH)
    assert result == {"id": SERIES_HASH, "title": "らーめん再遊記"}

    xml = (feeds_dir / f"{SERIES_HASH}.xml").read_text(encoding="utf-8")
    assert "aaa111" in xml
    assert "ccc333" in xml
    assert "bbb222" not in xml
    assert "第2杯" not in xml
    assert "https://bigcomics.jp/episodes/aaa111" in xml


def test_filters_waitfree_episodes(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    """「待つと無料」エピソードは無料扱いせず除外する。"""
    html = _series_html(
        title="らーめん再遊記",
        episodes=[
            {"hash": "aaa111", "title": "第1杯", "date": "2024/01/01"},
            {"hash": "ddd444", "title": "第4杯", "date": "2024/02/15", "waitfree": "y"},
            {"hash": "ccc333", "title": "第3杯", "date": "2024/02/01"},
        ],
    )
    requests_mock.get(SERIES_URL, text=html)

    result = main.build_feed_for_series(main.create_session(), SERIES_HASH)
    assert result == {"id": SERIES_HASH, "title": "らーめん再遊記"}

    xml = (feeds_dir / f"{SERIES_HASH}.xml").read_text(encoding="utf-8")
    assert "aaa111" in xml
    assert "ccc333" in xml
    assert "ddd444" not in xml
    assert "第4杯" not in xml


def test_strips_g_hidden_prefix_from_title(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    html = _series_html(title="ゴルゴ13", episodes=[])
    requests_mock.get(SERIES_URL, text=html)

    result = main.build_feed_for_series(main.create_session(), SERIES_HASH)
    assert result == {"id": SERIES_HASH, "title": "ゴルゴ13"}


def test_returns_none_on_404(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    requests_mock.get(SERIES_URL, status_code=404)
    assert main.build_feed_for_series(main.create_session(), SERIES_HASH) is None
    assert not (feeds_dir / f"{SERIES_HASH}.xml").exists()


def test_returns_none_without_title(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    requests_mock.get(SERIES_URL, text="<html><body>no h1</body></html>")
    assert main.build_feed_for_series(main.create_session(), SERIES_HASH) is None


def test_real_fixture_yields_free_episodes(
    requests_mock: rm_module.Mocker, feeds_dir: Path
) -> None:
    """実際の bigcomics.jp の HTML スナップショットでパースが成立すること。"""
    fixture = FIXTURES / "5611422227f8d.html"
    requests_mock.get(SERIES_URL, text=fixture.read_text(encoding="utf-8"))

    result = main.build_feed_for_series(main.create_session(), SERIES_HASH)

    assert result is not None
    assert result["id"] == SERIES_HASH
    assert "らーめん再遊記" in result["title"]

    xml = (feeds_dir / f"{SERIES_HASH}.xml").read_text(encoding="utf-8")
    # 完全無料エピソードは含まれる
    assert "751ae35fb0c01" in xml  # 第1杯（無料）
    assert "652d6adda76f0" in xml  # 第136杯（無料）
    # 「待つと無料」エピソードは除外される
    assert "f04c6bf4a5181" not in xml  # 第5杯（待つと無料）
    assert "5a989dbb3b12d" not in xml  # 第4杯（待つと無料）
    # 有料エピソードは除外される
    assert "b23af2d27a7f6" not in xml  # 第138杯（有料）
