"""Tests for inline preview editing."""

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


# ----- yaml_path unit tests ----------------------------------------------

def test_set_by_path_dict_leaf():
    from yaml_path import set_by_path, get_by_path
    d = {"a": {"b": 1}}
    set_by_path(d, "a.b", 42)
    assert get_by_path(d, "a.b") == 42


def test_set_by_path_list_index():
    from yaml_path import set_by_path
    d = {"xs": [{"v": 1}, {"v": 2}]}
    set_by_path(d, "xs.1.v", 99)
    assert d["xs"][1]["v"] == 99


def test_set_by_path_replaces_list_element():
    from yaml_path import set_by_path
    d = {"items": ["a", "b", "c"]}
    set_by_path(d, "items.0", "z")
    assert d["items"] == ["z", "b", "c"]


def test_set_by_path_rejects_unknown_dict_leaf():
    """We don't auto-create leaves — a typo'd path is an error, not a new field."""
    from yaml_path import set_by_path
    import pytest
    with pytest.raises(KeyError):
        set_by_path({"a": {"b": 1}}, "a.typo", 5)


# ----- editable render ---------------------------------------------------

def test_render_html_editable_adds_contenteditable_and_data_path():
    from render import render_html
    p = {
        "identity": {"name": "X", "email": "x@y"},
        "summary": "Some summary.",
        "experience": [{
            "company": "Acme", "title": "Eng", "start": "2020", "end": "Present",
            "bullets": [{"text": "Did a thing.", "general": True}],
        }],
        "skills": [{"group": "G", "items": ["a", "b"]}],
        "education": [{"institution": "U", "degree": "BS", "field": "CS"}],
        "certifications": [],
    }
    html = render_html(p, editable=True, save_url="/save")
    assert 'contenteditable="true"' in html
    assert 'data-path="summary"' in html
    assert 'data-path="experience.0.bullets.0.text"' in html
    assert 'data-path="skills.0.items"' in html
    # the inline save script
    assert "/save" in html
    assert "addEventListener" in html


def test_render_html_default_is_not_editable():
    from render import render_html
    p = {"identity": {"name": "X", "email": "x@y"}, "summary": "S"}
    html = render_html(p)
    assert "contenteditable" not in html
    assert "data-path" not in html


# ----- route: edit-field -------------------------------------------------

def _make_job(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "A", "role": "B"})
    return next((fake_root / "jobs").iterdir()).name


def test_edit_field_updates_summary(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/edit-field",
                    data=json.dumps({"path": "summary", "text": "A new summary."}),
                    content_type="application/json")
    assert r.status_code == 200, r.data
    saved = yaml.safe_load(
        (fake_root / "jobs" / slug / "resume-source.yaml").read_text()
    )
    assert saved["summary"] == "A new summary."


def test_edit_field_creates_resume_source_from_kitchen_sink(client, fake_root):
    """First edit on a fresh job auto-creates resume-source.yaml seeded from
    the kitchen sink."""
    slug = _make_job(client, fake_root)
    assert not (fake_root / "jobs" / slug / "resume-source.yaml").exists()
    client.post(f"/jobs/{slug}/edit-field",
                data=json.dumps({"path": "identity.name", "text": "Edited Name"}),
                content_type="application/json")
    saved = yaml.safe_load(
        (fake_root / "jobs" / slug / "resume-source.yaml").read_text()
    )
    assert saved["identity"]["name"] == "Edited Name"
    # Other fields preserved from kitchen sink:
    assert saved["experience"][0]["company"] == "TestCo"


def test_edit_field_bullet_text(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/edit-field",
                    data=json.dumps({"path": "experience.0.bullets.0.text",
                                     "text": "Brand new bullet text."}),
                    content_type="application/json")
    assert r.status_code == 200
    saved = yaml.safe_load(
        (fake_root / "jobs" / slug / "resume-source.yaml").read_text()
    )
    assert saved["experience"][0]["bullets"][0]["text"] == "Brand new bullet text."


def test_edit_field_skill_items_splits_on_commas(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/edit-field",
                    data=json.dumps({"path": "skills.0.items",
                                     "text": "Python, Go, Rust"}),
                    content_type="application/json")
    assert r.status_code == 200
    saved = yaml.safe_load(
        (fake_root / "jobs" / slug / "resume-source.yaml").read_text()
    )
    assert saved["skills"][0]["items"] == ["Python", "Go", "Rust"]


def test_edit_field_rejects_missing_path(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/edit-field",
                    data=json.dumps({"text": "x"}),
                    content_type="application/json")
    assert r.status_code == 400


def test_edit_field_rejects_unknown_leaf(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/edit-field",
                    data=json.dumps({"path": "identity.nonexistent_field",
                                     "text": "x"}),
                    content_type="application/json")
    assert r.status_code == 400


# ----- route: resume-edit page -------------------------------------------

def test_resume_edit_page_renders_editable_html(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.get(f"/jobs/{slug}/resume-edit.html")
    assert r.status_code == 200
    assert r.content_type.startswith("text/html")
    body = r.get_data(as_text=True)
    assert 'contenteditable="true"' in body
    assert 'data-path=' in body
    # The save URL is the edit-field endpoint for this slug
    assert f"/jobs/{slug}/edit-field" in body


def test_job_page_shows_edit_mode_toggle(client, fake_root):
    """The Preview/Edit toggle should appear once a job has any resume content."""
    slug = _make_job(client, fake_root)
    # Build first so has_html=True triggers the preview card
    client.post(f"/jobs/{slug}/build")
    body = client.get(f"/jobs/{slug}").get_data(as_text=True)
    assert "mode-edit" in body
    assert "Edit inline" in body
