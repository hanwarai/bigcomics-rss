"""parse_episode のフィルタリング仕様テスト。"""

from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup, Tag

import main


def _anchor(
    href: str = "/episodes/b23af2d27a7f6",
    title: str = "第138杯",
    date_text: str = "2026/05/08",
    paid: bool = False,
    waitfree: bool = False,
) -> Tag:
    paid_html = (
        '<div class="series-eplist-item-access-paid">'
        '<img src="/images/icons/coin.svg" alt="コイン" /></div>'
        if paid
        else ""
    )
    waitfree_html = (
        '<svg class="series-eplist-item-access-icon" data-e2e="eliWfIcon"></svg>'
        if waitfree
        else ""
    )
    html = (
        f'<a class="series-eplist-item-link" href="{href}">'
        f'<span class="series-eplist-item-h-text">{title}</span>'
        f'<div class="series-eplist-item-meta-date">{date_text}</div>'
        f"{paid_html}"
        f"{waitfree_html}"
        "</a>"
    )
    soup = BeautifulSoup(html, "html.parser")
    anchor = soup.find("a")
    assert isinstance(anchor, Tag)
    return anchor


def test_returns_none_when_paid() -> None:
    assert main.parse_episode(_anchor(paid=True)) is None


def test_returns_none_when_waitfree() -> None:
    """「待つと無料」（eliWfIcon）は今すぐ無料ではないので除外。"""
    assert main.parse_episode(_anchor(waitfree=True)) is None


def test_returns_none_when_href_invalid() -> None:
    assert main.parse_episode(_anchor(href="/other/abc")) is None
    assert main.parse_episode(_anchor(href="https://example.com/episodes/abc")) is None


def test_returns_none_when_title_missing() -> None:
    html = (
        '<a class="series-eplist-item-link" href="/episodes/b23af2d27a7f6">'
        '<div class="series-eplist-item-meta-date">2026/05/08</div></a>'
    )
    anchor = BeautifulSoup(html, "html.parser").find("a")
    assert isinstance(anchor, Tag)
    assert main.parse_episode(anchor) is None


def test_returns_none_on_invalid_date() -> None:
    assert main.parse_episode(_anchor(date_text="not a date")) is None
    assert main.parse_episode(_anchor(date_text="")) is None


def test_parses_free_episode() -> None:
    parsed = main.parse_episode(_anchor())
    assert parsed is not None
    assert parsed["unique_id"] == "b23af2d27a7f6"
    assert parsed["title"] == "第138杯"
    assert parsed["link"] == "https://bigcomics.jp/episodes/b23af2d27a7f6"
    assert parsed["pubdate"] == datetime(
        2026, 5, 8, tzinfo=timezone(timedelta(hours=9))
    )
