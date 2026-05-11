from __future__ import annotations

import argparse
import json
import math
import os
import re
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
BOUNTY_LIKE_PATTERNS = (
    "bounty",
    "earn",
    "reward",
    "token",
    "airdrop",
    "star +",
    "stars",
    "upvote",
    "reaction",
    "review an open pr",
    "google search console",
)


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


@dataclass(frozen=True)
class RankResult:
    issues: list[RankedIssue]
    skipped: dict[str, int]


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


def normalized_labels(item: dict[str, Any]) -> set[str]:
    return {label["name"].lower() for label in item.get("labels", [])}


def is_bounty_like(item: dict[str, Any]) -> bool:
    labels = normalized_labels(item)
    if any("bounty" in label for label in labels):
        return True

    text = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("body") or ""),
            " ".join(labels),
        ]
    ).lower()
    return any(pattern in text for pattern in BOUNTY_LIKE_PATTERNS)


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
    exclude_repos: set[str] | None = None,
    exclude_title_regex: str | None = None,
    exclude_bounty_like: bool = False,
) -> RankResult:
    repo_cache: dict[str, RepoDetails] = {}
    ranked = []
    skipped = {
        "repository": 0,
        "title": 0,
        "bounty_like": 0,
    }
    excluded = {repo.lower() for repo in exclude_repos or set()}
    title_re = re.compile(exclude_title_regex, re.IGNORECASE) if exclude_title_regex else None

    for item in items:
        repo = repo_from_url(item["repository_url"])
        if repo.lower() in excluded:
            skipped["repository"] += 1
            continue
        if title_re and title_re.search(str(item.get("title") or "")):
            skipped["title"] += 1
            continue
        if exclude_bounty_like and is_bounty_like(item):
            skipped["bounty_like"] += 1
            continue

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
    return RankResult(
        issues=sorted(ranked, key=lambda issue: issue.score, reverse=True),
        skipped=skipped,
    )


def _format_labels(labels: tuple[str, ...]) -> str:
    if not labels:
        return ""
    return " ".join(f"`{label}`" for label in sorted(labels))


def emit_text(result: RankResult) -> None:
    print(f"{'score':>6}  {'stars':>7}  {'repo':<32}  issue")
    for issue in result.issues:
        repo = issue.repo[:32]
        print(f"{issue.score:>6.1f}  {issue.stars:>7}  {repo:<32}  {issue.title}")
        print(f"{'':>6}  {'':>7}  {'':<32}  {issue.url}")
    skipped = {key: value for key, value in result.skipped.items() if value}
    if skipped:
        print(f"\nskipped: {json.dumps(skipped, sort_keys=True)}")


def emit_markdown(result: RankResult) -> None:
    print("# hubsignal scan results\n")
    for i, issue in enumerate(result.issues, 1):
        labels = _format_labels(issue.labels)
        print(f"### {i}. [{issue.title}]({issue.url})")
        print(f"- **Repository:** `{issue.repo}`")
        print(f"- **Stars:** {issue.stars}")
        print(f"- **Comments:** {issue.comments}")
        if labels:
            print(f"- **Labels:** {labels}")
        print()
    skipped = {key: value for key, value in result.skipped.items() if value}
    if skipped:
        print("---\n")
        print("### Skipped\n")
        for key, count in sorted(skipped.items()):
            print(f"- {key}: {count}")
        print()


def emit_json(result: RankResult) -> None:
    print(
        json.dumps(
            {
                "issues": [issue.__dict__ for issue in result.issues],
                "skipped": result.skipped,
            },
            indent=2,
        )
    )


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
        "--exclude-repo",
        action="append",
        default=[],
        metavar="OWNER/NAME",
        help="Drop issues from this repository. Can be repeated.",
    )
    parser.add_argument(
        "--exclude-title-regex",
        help="Drop issues whose title matches this Python regular expression.",
    )
    parser.add_argument(
        "--exclude-bounty-like",
        action="store_true",
        help="Drop issues that look like bounties, token rewards, or promotion tasks.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
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
    if args.exclude_title_regex:
        try:
            re.compile(args.exclude_title_regex)
        except re.error as exc:
            print(f"--exclude-title-regex is invalid: {exc}", file=sys.stderr)
            return 2

    token = gh_token()
    try:
        result = rank_issues(
            search_issues(args.query, args.limit, token),
            token,
            min_stars=args.min_stars,
            exclude_archived=args.exclude_archived,
            exclude_forks=args.exclude_forks,
            pushed_after=args.pushed_after,
            exclude_repos=set(args.exclude_repo),
            exclude_title_regex=args.exclude_title_regex,
            exclude_bounty_like=args.exclude_bounty_like,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        emit_json(result)
    elif args.format == "markdown":
        emit_markdown(result)
    else:
        emit_text(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
