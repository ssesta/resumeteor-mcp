"""UX tests. No network — capture is disabled in tests."""

from pathlib import Path

import yaml


def test_index_empty(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "JobSearch" in body
    assert "No jobs yet" in body


def test_create_job_without_capture_creates_folder(client, fake_root):
    r = client.post(
        "/jobs",
        data={"url": "https://example.com/jobs/foo", "company": "Acme", "role": "Staff Engineer"},
        follow_redirects=False,
    )
    assert r.status_code == 302
    jobs = list((fake_root / "jobs").iterdir())
    assert len(jobs) == 1
    folder = jobs[0]
    assert folder.name.endswith("__Acme__Staff-Engineer")
    yml = yaml.safe_load((folder / "job.yaml").read_text())
    assert yml["url"] == "https://example.com/jobs/foo"
    assert yml["company"] == "Acme"
    assert yml["role"] == "Staff Engineer"
    assert yml["status"] == "drafting"


def test_create_job_requires_url(client):
    r = client.post("/jobs", data={"url": ""}, follow_redirects=True)
    assert r.status_code == 200
    assert "URL is required" in r.get_data(as_text=True)


def test_view_job_page_renders(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    r = client.get(f"/jobs/{slug}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Acme" in body
    assert "/tailor jobs/" in body  # surfaces slash command for Claude


def test_view_unknown_job_404(client):
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404


def test_save_job_description_persists(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    new_content = "# Job description\n\nSome new content."
    r = client.post(f"/jobs/{slug}/file/job-description.md",
                    data={"content": new_content}, follow_redirects=True)
    assert r.status_code == 200
    saved = (fake_root / "jobs" / slug / "job-description.md").read_text()
    assert saved == new_content


def test_save_disallowed_filename_rejected(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    r = client.post(f"/jobs/{slug}/file/something-else.md",
                    data={"content": "x"})
    assert r.status_code == 400


def test_build_job_produces_all_three_formats(client, fake_root):
    """Build emits .docx, .html, and .pdf siblings."""
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    r = client.post(f"/jobs/{slug}/build", follow_redirects=True)
    assert r.status_code == 200
    folder = fake_root / "jobs" / slug
    docx = folder / "resume.docx"
    html = folder / "resume.html"
    pdf = folder / "resume.pdf"
    assert docx.exists() and docx.stat().st_size > 5000
    assert html.exists() and html.stat().st_size > 500
    assert pdf.exists() and pdf.stat().st_size > 5000
    # HTML mentions content from the kitchen-sink fixture
    assert "Test User" in html.read_text()
    # PDF starts with %PDF magic
    assert pdf.read_bytes()[:4] == b"%PDF"


def test_download_resume_docx(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    client.post(f"/jobs/{slug}/build")
    r = client.get(f"/jobs/{slug}/resume.docx")
    assert r.status_code == 200
    assert r.content_type.startswith("application/vnd.openxmlformats")


def test_download_rebuilds_if_yaml_is_newer(client, fake_root, tmp_path):
    """Auto-rebuild on download protects against the 'I edited but the
    downloaded file still has the old content' trap."""
    import time
    import yaml as _yaml
    from docx import Document

    client.post("/jobs", data={"url": "https://example.com/x", "company": "A", "role": "B"})
    slug = next((fake_root / "jobs").iterdir()).name
    # Build once with kitchen-sink content (fixture name "Test User")
    client.post(f"/jobs/{slug}/build")
    docx_path = fake_root / "jobs" / slug / "resume.docx"
    original_mtime = docx_path.stat().st_mtime

    # Edit the YAML to change the name; bump mtime so it's newer than the docx.
    src = fake_root / "jobs" / slug / "resume-source.yaml"
    profile = _yaml.safe_load((fake_root / "kitchen-sink" / "profile.yaml").read_text())
    profile["identity"]["name"] = "Edited Name"
    src.write_text(_yaml.safe_dump(profile, sort_keys=False))
    # Make sure src mtime > docx mtime
    time.sleep(0.05)
    src.touch()

    # Downloading should rebuild before serving.
    r = client.get(f"/jobs/{slug}/resume.docx")
    assert r.status_code == 200
    assert docx_path.stat().st_mtime > original_mtime, "docx was not rebuilt"
    # And the rebuilt docx contains the new name.
    doc = Document(str(docx_path))
    assert any("EDITED NAME" in p.text or "Edited Name" in p.text for p in doc.paragraphs)


def test_download_resume_pdf(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    client.post(f"/jobs/{slug}/build")
    r = client.get(f"/jobs/{slug}/resume.pdf")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"


def test_serve_resume_html(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    client.post(f"/jobs/{slug}/build")
    r = client.get(f"/jobs/{slug}/resume.html")
    assert r.status_code == 200
    assert r.content_type.startswith("text/html")
    assert b"Test User" in r.data


def test_job_page_embeds_preview_after_build(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    slug = next((fake_root / "jobs").iterdir()).name
    client.post(f"/jobs/{slug}/build")
    r = client.get(f"/jobs/{slug}")
    body = r.get_data(as_text=True)
    assert "Preview" in body
    assert f"/jobs/{slug}/resume.html" in body


def test_general_page_renders(client):
    r = client.get("/general")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "kitchen sink" in body.lower()


def test_general_build_produces_all_three(client, fake_root):
    r = client.post("/general/build", follow_redirects=True)
    assert r.status_code == 200
    base = fake_root / "general-resume"
    docx = base / "general-resume.docx"
    html = base / "general-resume.html"
    pdf = base / "general-resume.pdf"
    assert docx.exists() and docx.stat().st_size > 5000
    assert html.exists() and html.stat().st_size > 500
    assert pdf.exists() and pdf.read_bytes()[:4] == b"%PDF"


def test_general_serve_html(client, fake_root):
    client.post("/general/build")
    r = client.get("/general/resume.html")
    assert r.status_code == 200
    assert r.content_type.startswith("text/html")


def test_general_serve_pdf(client, fake_root):
    client.post("/general/build")
    r = client.get("/general/resume.pdf")
    assert r.status_code == 200
    assert r.content_type == "application/pdf"


def test_general_page_embeds_preview(client, fake_root):
    client.post("/general/build")
    r = client.get("/general")
    body = r.get_data(as_text=True)
    assert "Preview" in body
    assert "/general/resume.html" in body


def test_save_kitchen_sink_persists(client, fake_root):
    new_yaml = "identity:\n  name: New Name\n"
    r = client.post("/general/kitchen-sink",
                    data={"content": new_yaml}, follow_redirects=True)
    assert r.status_code == 200
    saved = (fake_root / "kitchen-sink" / "profile.yaml").read_text()
    assert saved == new_yaml


def test_jobs_listed_on_index_after_creation(client, fake_root):
    client.post("/jobs", data={"url": "https://example.com/x", "company": "Acme", "role": "PM"})
    r = client.get("/")
    body = r.get_data(as_text=True)
    assert "Acme" in body
    assert "PM" in body


def test_path_traversal_rejected(client):
    r = client.get("/jobs/..%2F..%2Fetc")
    assert r.status_code in (404, 308)
