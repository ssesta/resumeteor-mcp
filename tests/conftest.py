import os
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A self-contained project root with kitchen-sink/profile.yaml populated."""
    (tmp_path / "kitchen-sink").mkdir()
    (tmp_path / "kitchen-sink" / "linkedin").mkdir()
    (tmp_path / "general-resume").mkdir()
    (tmp_path / "jobs").mkdir()

    profile = {
        "identity": {
            "name": "Test User",
            "headline": "Test Headline",
            "email": "test@example.com",
            "linkedin": "https://www.linkedin.com/in/test/",
            "location": "Test City, ST",
        },
        "summary": "A short summary used only in tests.",
        "experience": [
            {
                "company": "TestCo",
                "location": "Remote",
                "title": "Senior Engineer",
                "start": "2022-01",
                "end": "Present",
                "bullets": [
                    {"text": "Built thing A that did X.", "tags": ["platform"]},
                    {"text": "Led team of N to deliver Y.", "tags": ["leadership"]},
                ],
            }
        ],
        "skills": [
            {"group": "Languages", "items": ["Python", "Go"]},
            {"group": "Cloud", "items": ["AWS", "GCP"]},
        ],
        "education": [
            {"institution": "Test University", "degree": "B.S.",
             "field": "Computer Science", "start": "2010", "end": "2014"}
        ],
        "certifications": [],
    }
    (tmp_path / "kitchen-sink" / "profile.yaml").write_text(
        yaml.safe_dump(profile, sort_keys=False)
    )
    return tmp_path


@pytest.fixture
def app(fake_root, monkeypatch):
    monkeypatch.setenv("JOBSEARCH_ROOT", str(fake_root))
    # Reset any cached env-derived state in script modules
    for m in ("build_resume", "new_job", "capture_job"):
        if m in sys.modules:
            del sys.modules[m]
    if "ui.app" in sys.modules:
        del sys.modules["ui.app"]
    from ui.app import create_app
    app = create_app(root=fake_root)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()
