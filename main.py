"""ビッコミ（bigcomics.jp）の無料エピソードを Atom フィードとして生成する。"""

from __future__ import annotations

import csv
import logging
import re
from collections.abc import Iterator
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedgenerator
import requests
from bs4 import BeautifulSoup, Tag
from jinja2 import Environment, FileSystemLoader
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("bigcomics-rss")

BASE_URL = "https://bigcomics.jp"
SERIES_URL_TEMPLATE = f"{BASE_URL}/series/{{series_hash}}"
EPISODE_URL_TEMPLATE = f"{BASE_URL}/episodes/{{episode_hash}}"
REQUEST_TIMEOUT = 15
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

SERIES_HASH_RE = re.compile(r"^[0-9a-f]{13}$")
EPISODE_HREF_RE = re.compile(r"^/episodes/([0-9a-f]+)$")

JST = timezone(timedelta(hours=9))

FEEDS_DIR = Path("feeds")
FEED_LIST_PATH = Path("feed.csv")
TEMPLATE_DIR = Path("templates")


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def extract_series_title(soup: BeautifulSoup) -> str | None:
    """`<h1 class="series-h-title">` から `<span class="g-hidden">` 接頭辞を除いたタイトル。"""
    h1 = soup.find("h1", class_="series-h-title")
    if h1 is None or not isinstance(h1, Tag):
        return None
    # g-hidden は SEO/スクリーンリーダー向けの「ビッコミの」接頭辞。削除して残りを採用
    for hidden in h1.find_all(class_="g-hidden"):
        hidden.extract()
    title = h1.get_text(strip=True)
    return title or None


def extract_cover_image(soup: BeautifulSoup) -> str | None:
    img = soup.find("img", class_="series-cover-image")
    if img is None or not isinstance(img, Tag):
        return None
    src = img.get("src")
    if isinstance(src, str) and src:
        return src
    return None


def parse_episode(anchor: Tag) -> dict[str, object] | None:
    """1 エピソードの `<a>` から dict を組み立てる。有料 / パース不能なら None。"""
    # 有料マーカー（コインアイコン）があれば除外
    if anchor.find("div", class_="series-eplist-item-access-paid") is not None:
        return None

    href = anchor.get("href")
    if not isinstance(href, str):
        return None
    m = EPISODE_HREF_RE.match(href)
    if m is None:
        return None
    episode_hash = m.group(1)

    title_el = anchor.find("span", class_="series-eplist-item-h-text")
    if title_el is None or not isinstance(title_el, Tag):
        return None
    title = title_el.get_text(strip=True)
    if not title:
        return None

    date_el = anchor.find("div", class_="series-eplist-item-meta-date")
    if date_el is None or not isinstance(date_el, Tag):
        return None
    date_text = date_el.get_text(strip=True)
    try:
        pubdate = datetime.strptime(date_text, "%Y/%m/%d").replace(tzinfo=JST)
    except ValueError:
        return None

    return {
        "unique_id": episode_hash,
        "title": title,
        "link": EPISODE_URL_TEMPLATE.format(episode_hash=episode_hash),
        "pubdate": pubdate,
    }


def build_feed_for_series(
    session: requests.Session, series_hash: str
) -> dict[str, str] | None:
    series_url = SERIES_URL_TEMPLATE.format(series_hash=series_hash)
    logger.info("%s %s", series_hash, series_url)

    response = session.get(series_url, timeout=REQUEST_TIMEOUT)
    if not response.ok:
        logger.warning(
            "failed to retrieve %s (status=%s)", series_hash, response.status_code
        )
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    title = extract_series_title(soup)
    if not title:
        logger.warning("no title for %s", series_hash)
        return None
    cover = extract_cover_image(soup)

    rss = feedgenerator.Atom1Feed(
        title=title,
        link=series_url,
        description="",
        language="ja",
        image=cover,
    )

    free_count = 0
    for anchor in soup.find_all("a", class_="series-eplist-item-link"):
        if not isinstance(anchor, Tag):
            continue
        parsed = parse_episode(anchor)
        if parsed is None:
            continue
        rss.add_item(
            unique_id=str(parsed["unique_id"]),
            title=str(parsed["title"]),
            link=str(parsed["link"]),
            description="",
            pubdate=parsed["pubdate"],
            content="",
        )
        free_count += 1

    logger.info("%s %s (%d free episodes)", series_hash, title, free_count)

    FEEDS_DIR.mkdir(exist_ok=True)
    with (FEEDS_DIR / f"{series_hash}.xml").open("w", encoding="utf-8") as fp:
        rss.write(fp, "utf-8")

    return {"id": series_hash, "title": title}


def read_feed_ids(path: Path) -> Iterator[str]:
    seen: set[str] = set()
    with path.open(encoding="utf-8") as fp:
        for row in csv.reader(fp):
            if not row:
                continue
            series_hash = row[0].strip()
            if not series_hash:
                continue
            if not SERIES_HASH_RE.fullmatch(series_hash):
                logger.warning("invalid series hash %r, skipping", series_hash)
                continue
            if series_hash in seen:
                logger.warning("duplicate series hash %r, skipping", series_hash)
                continue
            seen.add(series_hash)
            yield series_hash


def render_index(feeds: list[dict[str, str]]) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("index.html")
    FEEDS_DIR.mkdir(exist_ok=True)
    (FEEDS_DIR / "index.html").write_text(
        template.render(feeds=feeds), encoding="utf-8"
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    session = create_session()
    rendered: list[dict[str, str]] = []
    for series_hash in read_feed_ids(FEED_LIST_PATH):
        try:
            result = build_feed_for_series(session, series_hash)
        except Exception:
            logger.exception("failed to build feed for %s", series_hash)
            continue
        if result:
            rendered.append(result)
    render_index(rendered)


if __name__ == "__main__":
    main()
