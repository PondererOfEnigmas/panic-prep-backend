# tests/test_file_store.py
import importlib
import os
from pathlib import Path

import pytest

MODULE = "src.utils.file_store"


def reload_module(**env):
    orig_env = os.environ.copy()
    os.environ.update(env)
    try:
        return importlib.reload(importlib.import_module(MODULE))
    finally:
        os.environ.clear()
        os.environ.update(orig_env)


def test_allow_all_flag(monkeypatch):
    monkeypatch.setenv("PANDOC_ALLOW_ALL_FILES", "true")

    # Import (or reload) after the env var is in place
    mod = importlib.reload(importlib.import_module("src.utils.file_store"))

    assert mod.allowed_file("whatever.exe")


def test_reject_unknown_ext(monkeypatch):
    # Simulate pandoc reported only 'docx'
    monkeypatch.setattr(f"{MODULE}._PANDOC_INPUT_FORMATS", {"docx"}, raising=False)
    mod = importlib.import_module(MODULE)

    assert mod.allowed_file("report.docx")
    assert not mod.allowed_file("video.mkv")
