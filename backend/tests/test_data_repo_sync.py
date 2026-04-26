from pathlib import Path

import pytest

from app.config import settings
from app.services.data_repo_sync import DataRepo, configured_data_repos, sync_data_repo


def test_data_repo_config_points_to_official_repo_roots():
    repos = configured_data_repos()
    paths_by_name = {repo.name: repo.path for repo in repos}

    assert paths_by_name["SCED-downloads"] == settings.project_root / settings.sced_downloads
    assert paths_by_name["SCED"] == settings.project_root / settings.sced_repo
    assert paths_by_name["SCED"].name == "SCED"
    assert paths_by_name["SCED-downloads"].name == "SCED-downloads"
    assert "卡牌数据库" not in paths_by_name


@pytest.mark.asyncio
async def test_sync_data_repo_skips_missing_repo(tmp_path):
    result = await sync_data_repo(DataRepo("missing", tmp_path / "not-exists"))

    assert result["status"] == "missing"


@pytest.mark.asyncio
async def test_sync_data_repo_skips_non_git_repo(tmp_path):
    result = await sync_data_repo(DataRepo("plain", tmp_path))

    assert result["status"] == "not_git_repo"


def test_periodic_sync_only_includes_official_readonly_repos():
    repos = configured_data_repos()
    names = {repo.name for repo in repos}

    assert names == {"SCED-downloads", "SCED"}
    assert "卡牌数据库" not in names
    assert "arkham-card-maker" not in names
