"""feed.csv パース関数 read_feed_ids の仕様テスト。"""

from pathlib import Path

import pytest

import main


def _write(tmp_path: Path, content: str) -> Path:
    csv_path = tmp_path / "feed.csv"
    csv_path.write_text(content)
    return csv_path


def test_reads_valid_series_hashes(tmp_path: Path) -> None:
    path = _write(tmp_path, "5611422227f8d\nd65521c8caf23\n")
    assert list(main.read_feed_ids(path)) == ["5611422227f8d", "d65521c8caf23"]


def test_skips_empty_lines_and_whitespace(tmp_path: Path) -> None:
    path = _write(tmp_path, "5611422227f8d\n\n   \nd65521c8caf23\n")
    assert list(main.read_feed_ids(path)) == ["5611422227f8d", "d65521c8caf23"]


def test_skips_invalid_hashes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _write(
        tmp_path,
        "5611422227f8d\n../etc/passwd\nfoo\nABCDEF1234567\nd65521c8caf23\n",
    )
    with caplog.at_level("WARNING", logger="bigcomics-rss"):
        assert list(main.read_feed_ids(path)) == [
            "5611422227f8d",
            "d65521c8caf23",
        ]
    assert any("invalid series hash" in rec.message for rec in caplog.records)


def test_rejects_wrong_length_hash(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # 12 桁・14 桁はいずれも不正
    path = _write(tmp_path, "5611422227f8\n5611422227f8de\n")
    with caplog.at_level("WARNING", logger="bigcomics-rss"):
        assert list(main.read_feed_ids(path)) == []


def test_deduplicates_repeated_hashes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _write(
        tmp_path,
        "5611422227f8d\nd65521c8caf23\n5611422227f8d\nd65521c8caf23\nb14d95232f3a4\n",
    )
    with caplog.at_level("WARNING", logger="bigcomics-rss"):
        assert list(main.read_feed_ids(path)) == [
            "5611422227f8d",
            "d65521c8caf23",
            "b14d95232f3a4",
        ]
    assert sum("duplicate series hash" in rec.message for rec in caplog.records) == 2


def test_uses_only_first_column(tmp_path: Path) -> None:
    path = _write(tmp_path, "5611422227f8d,extra,columns\nd65521c8caf23,ignored\n")
    assert list(main.read_feed_ids(path)) == ["5611422227f8d", "d65521c8caf23"]


def test_strips_surrounding_whitespace(tmp_path: Path) -> None:
    path = _write(tmp_path, "  5611422227f8d  \n")
    assert list(main.read_feed_ids(path)) == ["5611422227f8d"]
