from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


API_ROOT = "https://api.github.com"
DEFAULT_QUERY = 'is:issue is:open label:"help wanted"'


@dataclass(frozen=True)
class RepoDetails:
    name: str
    stars: int
    archived: bool
    fork: bool
    pushed_at: str | None


@dataclass(frozen=True)
class RankedIssue:
    score: float
    repo: str
    title: str
    url: str
    labels: tuple[str, ...]
    comments: int
    updated_at: str
    stars: int
    archived: bool
    fork: bool
    pushed_at: str | None


def gh_token() -> str | None:
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    token = result.stdout.strip()
    return token or None


def github_get(path: str, token: str | None) -> dict[str, Any]:
    request = urllib.request.Request(f"{API_ROOT}{path}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "hubsignal/0.1")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API error {exc.code}: {body}") from exc


def search_issues(query: str, limit: int, token: str | None) -> list[dict[str, Any]]:
    encoded = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": min(limit, 100),
        }
    )
    data = github_get(f"/search/issues?{encoded}", token)
    return list(data.get("items", []))[:limit]


def repo_from_url(repository_url: str) -> str:
    prefix = f"{API_ROOT}/repos/"
    if not repository_url.startswith(prefix):
        return repository_url.rsplit("/", 2)[-1]
    return repository_url[len(prefix) :]


def repo_details(repo: str, token: str | None, cache: dict[str, RepoDetails]) -> RepoDetails:
    if repo not in cache:
        data = github_get(f"/repos/{repo}", token)
        cache[repo] = RepoDetails(
            name=repo,
            stars=int(data.get("stargazers_count") or 0),
            archived=bool(data.get("archived")),
            fork=bool(data.get("fork")),
            pushed_at=data.get("pushed_at"),
        )
    return cache[repo]


def days_since(iso_date: str) -> float:
    updated = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    return max(0.0, (datetime.now(timezone.utc) - updated).total_seconds() / 86400.0)


def score_issue(item: dict[str, Any], stars: int) -> float:
    labels = {label["name"].lower() for label in item.get("labels", [])}
    comments = int(item.get("comments") or 0)
    age_days = days_since(item["updated_at"])

    score = 20.0
    score += min(35.0, math.log10(stars + 1) * 9.0)
    score += max(0.0, 18.0 - age_days * 0.35)
    score += min(10.0, math.log2(comments + 1) * 2.0)

    if "help wanted" in labels:
        score += 10.0
    if "good first issue" in labels:
        score += 6.0
    if "bounty" in labels or any("bounty" in label for label in labels):
        score += 12.0
    if any("bug" == label or label.startswith("bug:") for label in labels):
        score += 3.0

    return round(score, 2)


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    if len(value) == 10:
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def repo_passes_filters(
    details: RepoDetails,
    min_stars: int,
    exclude_archived: bool,
    exclude_forks: bool,
    pushed_after: str | None,
) -> bool:
    if details.stars < min_stars:
        return False
    if exclude_archived and details.archived:
        return False
    if exclude_forks and details.fork:
        return False
    if pushed_after:
        pushed_at = parse_date(details.pushed_at)
        cutoff = parse_date(pushed_after)
        if pushed_at is None or cutoff is None or pushed_at < cutoff:
            return False
    return True


def rank_issues(
    items: list[dict[str, Any]],
    token: str | None,
    min_stars: int = 0,
    exclude_archived: bool = False,
    exclude_forks: bool = False,
    pushed_after: str | None = None,
) -> list[RankedIssue]:
    repo_cache: dict[str, RepoDetails] = {}
    ranked = []
    for item in items:
        repo = repo_from_url(item["repository_url"])
        details = repo_details(repo, token, repo_cache)
        if not repo_passes_filters(
            details,
            min_stars=min_stars,
            exclude_archived=exclude_archived,
            exclude_forks=exclude_forks,
            pushed_after=pushed_after,
        ):
            continue
        labels = tuple(label["name"] for label in item.get("labels", []))
        ranked.append(
            RankedIssue(
                score=score_issue(item, details.stars),
                repo=repo,
                title=item["title"],
                url=item["html_url"],
                labels=labels,
                comments=int(item.get("comments") or 0),
                updated_at=item["updated_at"],
                stars=details.stars,
                archived=details.archived,
                fork=details.fork,
                pushed_at=details.pushed_at,
            )
        )
    return sorted(ranked, key=lambda issue: issue.score, reverse=True)


def emit_text(issues: list[RankedIssue]) -> None:
    print(f"{'score':>6}  {'stars':>7}  {'repo':<32}  issue")
    for issue in issues:
        repo = issue.repo[:32]
        print(f"{issue.score:>6.1f}  {issue.stars:>7}  {repo:<32}  {issue.title}")
        print(f"{'':>6}  {'':>7}  {'':<32}  {issue.url}")


def emit_json(issues: list[RankedIssue]) -> None:
    print(json.dumps([issue.__dict__ for issue in issues], indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank promising GitHub issues.")
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help=f"GitHub issue search query. Default: {DEFAULT_QUERY!r}",
    )
    parser.add_argument("--limit", type=int, default=20, help="Number of issues to inspect.")
    parser.add_argument(
        "--min-stars",
        type=int,
        default=0,
        help="Drop issues from repositories below this star count.",
    )
    parser.add_argument(
        "--exclude-archived",
        action="store_true",
        help="Drop issues from archived repositories.",
    )
    parser.add_argument(
        "--exclude-forks",
        action="store_true",
        help="Drop issues from fork repositories.",
    )
    parser.add_argument(
        "--pushed-after",
        metavar="YYYY-MM-DD",
        help="Drop issues from repositories with no push after this date.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1 or args.limit > 100:
        print("--limit must be between 1 and 100", file=sys.stderr)
        return 2
    if args.min_stars < 0:
        print("--min-stars must be non-negative", file=sys.stderr)
        return 2
    if args.pushed_after:
        try:
            parse_date(args.pushed_after)
        except ValueError:
            print("--pushed-after must use YYYY-MM-DD", file=sys.stderr)
            return 2

    token = gh_token()
    try:
        issues = rank_issues(
            search_issues(args.query, args.limit, token),
            token,
            min_stars=args.min_stars,
            exclude_archived=args.exclude_archived,
            exclude_forks=args.exclude_forks,
            pushed_after=args.pushed_after,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        emit_json(issues)
    else:
        emit_text(issues)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
