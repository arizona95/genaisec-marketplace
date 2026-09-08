#!/usr/bin/env python3
"""cli_*.py 공통 — 아카이브 경로 해소·flow 로딩·CLI 진입 보일러플레이트.

왜 있나: cli_dlp/cli_egress/cli_tenant/cli_tool 이 `repo_root()`·`resolve()` 를 각자 복붙해
jscpd 가 중복 4건으로 잡았다(2026-08). 경로 규칙이 한 곳에만 있어야 아카이브 레이아웃이
바뀔 때 한 번만 고친다.
"""
import glob
import json
import os
import sys

# 리뷰 대상 CLI 발신 트래픽을 고르는 user-agent 마커(대상마다 다르면 호출부에서 넘긴다).
UA_CLI = "claude-cli"


def repo_root():
    """SDSreviewBLUE 루트(이 스크립트는 aar-plugin/skills/scenario-capture/scripts 아래)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))


def resolve(arg):
    """`<env>/<archive-folder>` 또는 실제 디렉터리 경로 → 아카이브 디렉터리 절대경로."""
    if os.path.isdir(arg):
        return arg
    p = os.path.join(repo_root(), "runs", "envs", *arg.split("/"))
    if not os.path.isdir(p) and "/" in arg:
        env, folder = arg.split("/", 1)
        p = os.path.join(repo_root(), "runs", "envs", env, "captures", "archives", folder)
    return p


def archive_dir_from_argv(script_name):
    """CLI 인자 검사 + 경로 해소를 한 줄로. 인자가 없으면 usage 로 종료."""
    if len(sys.argv) < 2:
        sys.exit(f"usage: {script_name} <env>/<archive>")
    return resolve(sys.argv[1])


def iter_flows(d):
    """아카이브 폴더의 flow json 을 (경로, dict) 로 순회한다. 깨진 파일은 건너뛴다."""
    for fp in sorted(glob.glob(os.path.join(d, "*.json"))):
        try:
            with open(fp, encoding="utf-8") as f:
                yield fp, json.load(f)
        except Exception:
            continue
