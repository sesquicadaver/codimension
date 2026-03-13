# -*- coding: utf-8 -*-
#
# Codimension - Python 3 experimental IDE
# Copyright (C) 2025  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""GitHub REST API client for Git plugin.

Uses Personal Access Token (PAT) from gitconfig.
Docs: https://docs.github.com/en/rest
"""

import json
import re
import urllib.error
import urllib.request


def _get_owner_repo(git_root: str) -> tuple[str, str] | None:
    """Parse remote URL to get owner/repo. Returns (owner, repo) or None."""
    try:
        from .gitconfig import get_default_remote
        from .gitdriver import run_git

        remote = get_default_remote()
        stdout, _, code = run_git(git_root, ["remote", "get-url", remote])
        if code != 0:
            stdout, _, code = run_git(git_root, ["remote", "get-url", "origin"])
        if code != 0:
            stdout, _, code = run_git(git_root, ["remote", "get-url", "default"])
        if code != 0 or not stdout.strip():
            return None
        url = stdout.strip()
        # https://github.com/owner/repo.git or git@github.com:owner/repo.git
        m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", url)
        if m:
            return (m.group(1), m.group(2).removesuffix(".git"))
    except Exception:
        pass
    return None


def _api_request(
    method: str,
    path: str,
    token: str,
    data: dict | None = None,
) -> tuple[dict | list | None, str | None]:
    """Make GitHub API request. Returns (response_json, error_message)."""
    if not token:
        return None, "GitHub token not configured. Set it in Plugins → Git → Settings."
    url = "https://api.github.com" + path
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}, None
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            msg = err_json.get("message", err_body[:200])
        except Exception:
            msg = str(e)
        return None, f"GitHub API error {e.code}: {msg}"
    except urllib.error.URLError as e:
        return None, f"Network error: {e.reason}"
    except Exception as e:
        return None, str(e)


def get_repo_prs_url(git_root: str) -> str | None:
    """Return GitHub PRs page URL for the repo, or None."""
    pair = _get_owner_repo(git_root)
    if not pair:
        return None
    owner, repo = pair
    return f"https://github.com/{owner}/{repo}/pulls"


def create_pull_request(
    git_root: str,
    base: str,
    title: str,
    body: str = "",
) -> tuple[str | None, str | None]:
    """Create a pull request. Returns (html_url, error_message)."""
    pair = _get_owner_repo(git_root)
    if not pair:
        return None, "Could not determine GitHub owner/repo from remote."

    try:
        from .gitdriver import run_git

        stdout, _, code = run_git(git_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        if code != 0 or not stdout.strip():
            return None, "Could not determine current branch."
        head = stdout.strip()
    except Exception as e:
        return None, str(e)

    owner, repo = pair
    path = f"/repos/{owner}/{repo}/pulls"
    data = {"title": title, "head": head, "base": base}
    if body:
        data["body"] = body

    token = None
    try:
        from .gitconfig import get_github_token

        token = get_github_token()
    except ImportError:
        pass

    resp, err = _api_request("POST", path, token, data)
    if err:
        return None, err
    if resp and isinstance(resp, dict):
        return resp.get("html_url"), None
    return None, "Unexpected API response"


def list_pull_requests(git_root: str, state: str = "open") -> tuple[list | None, str | None]:
    """List pull requests. Returns (list of PR dicts, error_message)."""
    pair = _get_owner_repo(git_root)
    if not pair:
        return None, "Could not determine GitHub owner/repo from remote."
    owner, repo = pair
    path = f"/repos/{owner}/{repo}/pulls?state={state}&per_page=30"

    token = None
    try:
        from .gitconfig import get_github_token

        token = get_github_token()
    except ImportError:
        pass

    resp, err = _api_request("GET", path, token)
    if err:
        return None, err
    if isinstance(resp, list):
        return resp, None
    return None, "Unexpected API response"
