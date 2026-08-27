# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

bigcomics-rss は [ビッコミ (bigcomics.jp)](https://bigcomics.jp) の各シリーズの無料エピソードを Atom フィード形式で配信する Python スクリプト。生成されたフィードは GitHub Pages でホスティングされる。

## Commands

```bash
# 依存関係のインストール
uv sync --all-extras

# 型チェック
uv run mypy main.py

# テスト
uv run pytest

# フィード生成
uv run main.py
```

Python は `pyproject.toml` で `>=3.13` を要求し、`.python-version` も `3.13` にピン留め。CI では `actions/setup-python` が `python-version-file: pyproject.toml` を読んで `requires-python` を解決する。

## Architecture

### データフロー

1. `feed.csv` を読み込む（形式: `series_hash` の 1 カラム、13 桁 hex）
2. `series_hash` を `^[0-9a-f]{13}$` で検証し、不正な行はスキップ（出力パス経由の path traversal 防止）
3. 各シリーズに対して `https://bigcomics.jp/series/{series_hash}` を GET
4. BeautifulSoup で HTML をパース:
   - シリーズタイトル: `h1` 配下のテキスト（`span.g-hidden` 接頭辞を除外）
   - カバー画像: `img.series-cover-image` の `src`
   - エピソード: `a.series-eplist-item-link` を走査し、有料マーカー `div.series-eplist-item-access-paid`（コインアイコン）と「待つと無料」マーカー `[data-e2e="eliWfIcon"]`（待機アイコン）の **どちらも持たない** ものだけ採用（＝完全無料のみ）
   - エピソードタイトル: `span.series-eplist-item-h-text` のテキスト
   - エピソード公開日: `div.series-eplist-item-meta-date` の `YYYY/MM/DD` を JST 00:00 として解釈
5. `feedgenerator.Atom1Feed` で Atom フィードを生成 → `feeds/{series_hash}.xml`
6. Jinja2 (`autoescape=True`) で `templates/index.html` をレンダリング → `feeds/index.html`

### 主要ファイル

| ファイル | 役割 |
|---|---|
| `main.py` | スクレイピング + Atom 生成 + index.html 生成のオーケストレータ |
| `feed.csv` | 購読対象シリーズの定義（`series_hash` 1 カラム CSV） |
| `templates/index.html` | Jinja2 テンプレート。`feeds` 変数（`id`, `title` を持つ dict のリスト）を受け取る |
| `feeds/` | 出力ディレクトリ。`.gitkeep` 以外は ignore。GitHub Pages にデプロイされる |
| `tests/fixtures/` | 実 HTML スナップショット。bigcomics.jp の DOM 変化検出用 |

### 「無料」判定ロジック

bigcomics の各エピソード `<a>` の access 表示エリアは 3 種類:

| 種別 | マーカー | 採用 |
|---|---|---|
| 有料 | `div.series-eplist-item-access-paid`（コイン, `data-e2e="eliCoinIcon"`） | ✗ 除外 |
| 待つと無料 | `svg.series-eplist-item-access-icon`（`data-e2e="eliWfIcon"`） | ✗ 除外 |
| 完全無料 | `span.series-eplist-item-access-text.mode-free`（`data-e2e="eliFreeBadge"`, テキスト「無料」） | ✓ 採用 |

**判定**: 有料マーカー（`series-eplist-item-access-paid`）と「待つと無料」マーカー（`data-e2e="eliWfIcon"`）の **どちらも持たない** エピソード = 完全無料として採用。
「待つと無料」は今すぐ読めないため除外する（過去はこれを無料扱いに含めていたが、現在は除外）。
yanmaga の「無料タグの存在」と逆向きの判定（負条件）になっている点に注意。

### シリーズの追加方法

`feed.csv` に新しい行を追加する:

```
{series_hash}
```

`series_hash` は bigcomics.jp の作品 URL `/series/{hash}` 部分（13 桁 hex）。フィード XML のファイル名にもなる。

### CI/CD

ワークフローは 2 本。

**`.github/workflows/gh-pages.yaml`**（デプロイ）が以下のタイミングで自動実行:
- `main` ブランチへの push
- 12 時間ごと（cron）
- `workflow_dispatch`

build ジョブで `mypy` → `pytest` → `main.py` を実行し、`feeds/` を GitHub Pages にデプロイ。schedule 実行が失敗した場合は `ci-failure` ラベル付き Issue を自動作成・追記する（push 起因の失敗は Issue 化されない点に注意）。

**`.github/workflows/ci.yaml`**（PR チェック）は `main` を base とする `pull_request` で実行。`uv lock --check` → `uv sync --frozen --all-extras` → `mypy` → `pytest` のみを走らせる軽量ジョブで、`main.py` の実行（bigcomics.jp への実アクセス）と Pages デプロイは含まない。Dependabot PR もこれで検証される。

`uv sync --frozen` は `uv.lock` と `pyproject.toml` の整合性を検証しないため、`uv lock --check` を独立したステップとして持たせている。両ワークフローとも uv 本体のバージョンは `pyproject.toml` の `[dependency-groups] ci` ピンから読み取って `setup-uv` に渡す。
