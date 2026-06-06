"""Tests for the workflow state machine and custom-content surface."""

import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

# A real-ish job description to clear the "needs-description" threshold.
DESCRIPTION = (
    "# Senior Engineer\n\n"
    + ("We are looking for a senior engineer to lead our platform team. "
       "Required skills include Python and AWS. ") * 6
)


def _make_job(client, fake_root, company="Acme", role="PM"):
    client.post("/jobs", data={"url": "https://example.com/x",
                               "company": company, "role": role})
    return next((fake_root / "jobs").iterdir()).name


# --- derived state -------------------------------------------------------

def test_state_needs_description_when_blank(client, fake_root):
    slug = _make_job(client, fake_root)
    from status import derive_state
    st = derive_state(fake_root / "jobs" / slug)
    assert st.state == "needs-description"
    assert not st.is_explicit


def test_state_advances_to_needs_tailoring(client, fake_root):
    slug = _make_job(client, fake_root)
    (fake_root / "jobs" / slug / "job-description.md").write_text(DESCRIPTION)
    from status import derive_state
    assert derive_state(fake_root / "jobs" / slug).state == "needs-tailoring"


def test_state_advances_to_needs_build(client, fake_root):
    slug = _make_job(client, fake_root)
    (fake_root / "jobs" / slug / "job-description.md").write_text(DESCRIPTION)
    (fake_root / "jobs" / slug / "resume-source.yaml").write_text(
        "identity:\n  name: X\n  email: x@y\n"
        "summary: A summary.\n"
        "experience:\n  - company: A\n    title: B\n    start: '2020'\n    end: Present\n"
        "    bullets:\n      - text: Did stuff.\n"
        "education:\n  - institution: U\n    degree: BS\n    field: CS\n"
        "skills:\n  - group: G\n    items: [x]\n"
    )
    from status import derive_state
    assert derive_state(fake_root / "jobs" / slug).state == "needs-build"


def test_state_advances_to_needs_review_after_build(client, fake_root):
    slug = _make_job(client, fake_root)
    (fake_root / "jobs" / slug / "job-description.md").write_text(DESCRIPTION)
    client.post(f"/jobs/{slug}/build")  # builds from kitchen-sink fallback
    # Need to also create resume-source so we're not still in needs-tailoring
    (fake_root / "jobs" / slug / "resume-source.yaml").write_text(
        (fake_root / "kitchen-sink" / "profile.yaml").read_text()
    )
    # rebuild so resume.docx is newer than resume-source.yaml
    time.sleep(0.01)
    client.post(f"/jobs/{slug}/build")
    from status import derive_state
    assert derive_state(fake_root / "jobs" / slug).state == "needs-review"


# --- explicit state actions ----------------------------------------------

def test_set_explicit_state_ready(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/state", data={"state": "ready"},
                    follow_redirects=True)
    assert r.status_code == 200
    from status import derive_state
    st = derive_state(fake_root / "jobs" / slug)
    assert st.state == "ready"
    assert st.is_explicit


def test_clear_explicit_state_reverts_to_auto(client, fake_root):
    slug = _make_job(client, fake_root)
    client.post(f"/jobs/{slug}/state", data={"state": "submitted"})
    client.post(f"/jobs/{slug}/state", data={"state": "auto"})
    from status import derive_state
    st = derive_state(fake_root / "jobs" / slug)
    assert not st.is_explicit
    assert st.state == "needs-description"


def test_unknown_state_rejected(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/state", data={"state": "bogus"},
                    follow_redirects=True)
    assert b"Unknown state" in r.data


# --- custom content + promote --------------------------------------------

def test_save_custom_content_persists(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/custom-content",
                    data={"content": "Some job-specific story.\nMore detail."},
                    follow_redirects=True)
    assert r.status_code == 200
    saved = (fake_root / "jobs" / slug / "custom-content.md").read_text()
    assert "Some job-specific story" in saved


def test_promote_custom_appends_to_narrative_with_provenance(client, fake_root):
    slug = _make_job(client, fake_root)
    (fake_root / "kitchen-sink" / "narrative.md").write_text("# Narrative\n\nOriginal.\n")
    client.post(f"/jobs/{slug}/custom-content",
                data={"content": "Unique story XYZ-123."})
    r = client.post(f"/jobs/{slug}/promote-custom", follow_redirects=True)
    assert r.status_code == 200
    narrative = (fake_root / "kitchen-sink" / "narrative.md").read_text()
    assert "Original." in narrative                       # preserves existing content
    assert "Unique story XYZ-123." in narrative          # appended
    assert f"Promoted from {slug}" in narrative          # provenance header


def test_promote_empty_custom_warns(client, fake_root):
    slug = _make_job(client, fake_root)
    r = client.post(f"/jobs/{slug}/promote-custom", follow_redirects=True)
    body = r.get_data(as_text=True)
    assert "Nothing to promote" in body


# --- UX surfacing --------------------------------------------------------

def test_job_page_shows_state_and_next_step(client, fake_root):
    slug = _make_job(client, fake_root)
    body = client.get(f"/jobs/{slug}").get_data(as_text=True)
    assert "needs-description" in body
    assert "Paste or capture the job posting" in body
    assert "Mark approved" in body


def test_index_shows_state_badge(client, fake_root):
    _make_job(client, fake_root, company="Foo", role="Bar")
    body = client.get("/").get_data(as_text=True)
    assert "state-badge" in body
    assert "needs-description" in body
