from datetime import datetime, timedelta, timezone

from hubsignal.cli import (
    RepoDetails,
    is_bounty_like,
    rank_issues,
    repo_passes_filters,
    repo_from_url,
    score_issue,
)


def test_repo_from_url_extracts_owner_and_name():
    assert (
        repo_from_url("https://api.github.com/repos/owner/project")
        == "owner/project"
    )


def test_score_rewards_useful_signals():
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    item = {
        "updated_at": now,
        "comments": 8,
        "labels": [{"name": "help wanted"}, {"name": "bounty"}],
    }

    assert score_issue(item, stars=10_000) > score_issue(item, stars=10)


def test_score_decays_with_staleness():
    fresh = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    stale = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat().replace(
        "+00:00", "Z"
    )
    base = {"comments": 1, "labels": [{"name": "help wanted"}]}

    assert score_issue({**base, "updated_at": fresh}, 100) > score_issue(
        {**base, "updated_at": stale}, 100
    )


def test_repo_filters_apply_repository_metadata():
    details = RepoDetails(
        name="owner/project",
        stars=50,
        archived=False,
        fork=False,
        pushed_at="2026-05-01T00:00:00Z",
    )

    assert repo_passes_filters(details, 10, True, True, "2026-01-01")
    assert not repo_passes_filters(details, 100, True, True, "2026-01-01")
    assert not repo_passes_filters(details, 10, True, True, "2026-06-01")


def test_repo_filters_can_exclude_archived_and_forked_repos():
    details = RepoDetails(
        name="owner/project",
        stars=50,
        archived=True,
        fork=True,
        pushed_at="2026-05-01T00:00:00Z",
    )

    assert repo_passes_filters(details, 10, False, False, None)
    assert not repo_passes_filters(details, 10, True, False, None)
    assert not repo_passes_filters(details, 10, False, True, None)


def test_bounty_like_detection_checks_labels_title_and_body():
    assert is_bounty_like(
        {
            "title": "Find a typo",
            "body": "Earn tokens for a quick task",
            "labels": [{"name": "good first issue"}],
        }
    )
    assert is_bounty_like(
        {
            "title": "Add a dashboard",
            "body": "",
            "labels": [{"name": "bounty"}],
        }
    )
    assert not is_bounty_like(
        {
            "title": "Document CLI behavior",
            "body": "Small docs-only fix",
            "labels": [{"name": "documentation"}],
        }
    )


def test_rank_issues_reports_skipped_noise_without_fetching_repo_details(monkeypatch):
    items = [
        {
            "repository_url": "https://api.github.com/repos/noisy/project",
            "title": "Bounty: star + review an open PR",
            "body": "",
            "labels": [{"name": "good first issue"}],
            "comments": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "html_url": "https://github.com/noisy/project/issues/1",
        },
        {
            "repository_url": "https://api.github.com/repos/owner/project",
            "title": "Document CLI behavior",
            "body": "",
            "labels": [{"name": "documentation"}],
            "comments": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "html_url": "https://github.com/owner/project/issues/2",
        },
    ]

    def fake_repo_details(repo, token, cache):
        return RepoDetails(
            name=repo,
            stars=100,
            archived=False,
            fork=False,
            pushed_at="2026-05-01T00:00:00Z",
        )

    monkeypatch.setattr("hubsignal.cli.repo_details", fake_repo_details)

    result = rank_issues(items, token=None, exclude_bounty_like=True)

    assert len(result.issues) == 1
    assert result.issues[0].repo == "owner/project"
    assert result.skipped["bounty_like"] == 1
