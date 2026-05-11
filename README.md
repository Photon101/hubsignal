# hubsignal

Find promising open-source work on GitHub.

`hubsignal` is a small CLI that searches open GitHub issues and ranks them with simple, inspectable signals:

- repository stars
- issue labels such as `help wanted`, `good first issue`, and `bounty`
- freshness
- discussion volume

The goal is not to predict value perfectly. The goal is to reduce the first hour of manual scanning into a short, reviewable list.

## Install

For local development:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

No runtime dependencies are required.

## Authentication

Unauthenticated GitHub API calls are rate limited. For best results, authenticate one of these ways:

```bash
export GH_TOKEN=...
```

or install/login with GitHub CLI:

```bash
gh auth login
```

`hubsignal` will use `GH_TOKEN`, `GITHUB_TOKEN`, or `gh auth token`, in that order.

## Usage

```bash
hubsignal --query 'is:issue is:open label:"help wanted" language:Python' --limit 20
hubsignal --query 'is:issue is:open label:"good first issue" language:Go' --min-stars 100 --exclude-archived --exclude-forks --pushed-after 2026-01-01
hubsignal --query 'is:issue is:open label:"good first issue" language:Python' --exclude-bounty-like --exclude-repo noisy/project
hubsignal --query 'is:issue is:open "good first issue" "agent"' --format json
```

Example output:

```text
score  repo              issue
83.2   owner/project     Improve cache invalidation
      https://github.com/owner/project/issues/123
```

## Development

```bash
python -m pytest
python -m hubsignal --limit 5
```

## License

MIT
