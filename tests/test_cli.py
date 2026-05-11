from datetime import datetime, timedelta, timezone

from hubsignal.cli import RepoDetails, repo_passes_filters, repo_from_url, score_issue


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
