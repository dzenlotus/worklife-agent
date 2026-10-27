from worklife.workspace import Workspace


def test_job_observations_preserve_history_and_initial_discovery(tmp_path):
    w = Workspace(tmp_path)
    first = w.save_job(
        {
            "id": "1",
            "platform": "test",
            "title": "Engineer",
            "employer": "Example",
            "url": "https://example.org/jobs/1",
            "salary_min": 100,
        }
    )
    second = w.save_job({**first, "salary_min": 200})
    assert second["first_seen_at"] == first["first_seen_at"]
    assert second["last_seen_at"] >= first["last_seen_at"]
    observations = w.store.list("job_observation")
    assert len(observations) == 2
    assert sorted(row["job"]["salary_min"] for row in observations) == [100, 200]
    assert all(row["job_id"] == first["id"] for row in observations)


def test_saving_an_opportunity_does_not_require_a_resume(tmp_path):
    w = Workspace(tmp_path)
    job = w.save_job(
        {
            "id": "1",
            "platform": "test",
            "title": "Engineer",
            "employer": "Example",
            "url": "https://example.org/jobs/1",
        }
    )
    application = w.application(job["id"], None, "saved", "Selected for review")
    assert application["stage"] == "saved"
    assert application["cv_id"] is None
    w.save_profile({"facts": [{"id": "python", "text": "Python", "source": "Portfolio"}]})
    cv = w.create_cv("CV", ["python"], "Engineer")
    w.application(job["id"], cv["id"], "applied", "Observed application")
    assert w.application(job["id"], None, "reply", "Observed reply")["cv_id"] == cv["id"]
