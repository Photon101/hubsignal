# hubsignal

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-%23ea4aaa)](https://github.com/sponsors/Photon101)
[![CI](https://github.com/Photon101/hubsignal/actions/workflows/ci.yml/badge.svg)](https://github.com/Photon101/hubsignal/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/python-3.10%2B-blue)](https://github.com/Photon101/hubsignal)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Find promising open-source work on GitHub — in seconds, not hours.**

`hubsignal` is a zero-dependency CLI that scans GitHub issues and ranks them by signal strength. Stars, labels, freshness, and discussion activity all factor into a simple, inspectable score. No AI, no magic — just fast filtering of the GitHub issue firehose.

## Quick Start

```bash
git clone https://github.com/Photon101/hubsignal.git
cd hubsignal
uv run python -m hubsignal --limit 10
```

## What You Get

```
 score    stars  repo                              issue
────────────────────────────────────────────────────────────────────────────
  84.2      824  openjournals/joss-reviews         [REVIEW]: MaterForge: Materials Formulation Engine
                                                   https://github.com/openjournals/joss-reviews/issues/9909

  72.1    20473  microsoft/onnxruntime             Handle empty initializers gracefully in optimizer passes
                                                   https://github.com/microsoft/onnxruntime/pull/27976

  58.8      120  Consensys/linea-monorepo          [ZkTracer] Add test cases for blake.rs implementation
                                                   https://github.com/Consensys/linea-monorepo/pull/3011
```

Each issue gets a score from 0–100. Higher scores mean the issue is in an active, starred repo with useful labels and recent activity — the kind of issue where your contribution matters.

## Features

| Flag | What it does |
|---|---|
| `--min-stars N` | Only show repos with ≥N stars |
| `--exclude-archived` | Skip archived repositories |
| `--exclude-forks` | Skip forked repositories |
| `--exclude-bounty-like` | Filter out token promotions, star-for-reward, crypto noise |
| `--bounty-only` | Oppose of above — only show issues with bounties/rewards |
| `--exclude-repo OWNER/NAME` | Exclude specific repos (repeatable) |
| `--exclude-title-regex PATTERN` | Filter by title regex |
| `--pushed-after YYYY-MM-DD` | Only repos active after this date |
| `--format text\|json\|markdown` | Output as plain text, JSON, or Markdown report |
| `--limit N` | Number of issues to scan (1–100) |

## Real Use Cases

**Finding your first open-source contribution:**
```bash
hubsignal --query 'is:issue is:open label:"good first issue" label:documentation' \
  --min-stars 20 --exclude-archived --exclude-forks --exclude-bounty-like
```

**Hunting paid bounties:**
```bash
hubsignal --bounty-only --query 'label:bounty is:issue is:open' --limit 20
```

**Weekly planning report:**
```bash
hubsignal --limit 30 --format markdown > weekly-scout-$(date +%Y-%m-%d).md
```

**JSON export for your own tooling:**
```bash
hubsignal --format json | jq '.issues[] | {repo, url, score}'
```

## How Scoring Works

```
score = 20 (base)
      + min(35, log10(stars + 1) × 9)   ← repo popularity
      + max(0, 18 − age_days × 0.35)     ← issue freshness
      + min(10, log2(comments + 1) × 2)  ← discussion activity
      + 10 (if "help wanted" label)
      + 6  (if "good first issue" label)
      + 12 (if bounty/reward label)
      + 3  (if bug label)
```

Fully inspectable. No hidden weights. No AI. No API keys needed.

## Authentication

GitHub limits unauthenticated API requests. For best results:

```bash
export GH_TOKEN=your_github_token
# or install gh CLI and login:
gh auth login
```

`hubsignal` checks `GH_TOKEN`, `GITHUB_TOKEN`, then `gh auth token` — in that order.

## Install

```bash
git clone https://github.com/Photon101/hubsignal.git
cd hubsignal
uv run python -m hubsignal --help
```

Zero dependencies at runtime. pytest is optional for development.

## Why I Built This

I spent hours manually scrolling GitHub issue search looking for good first contributions. The signal-to-noise ratio is terrible — most issues are stale, claimed, or in dead repos. `hubsignal` cuts that first hour of scanning into a 30-second command.

## Sponsor

If `hubsignal` saves you time finding open-source work, consider [sponsoring on GitHub](https://github.com/sponsors/Photon101). Sponsorship funds sustained development and keeps the tool dependency-free and focused.

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-%E2%9D%A4-%23ea4aaa)](https://github.com/sponsors/Photon101)

## License

MIT
