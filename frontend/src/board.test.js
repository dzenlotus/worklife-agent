import test from "node:test";
import assert from "node:assert/strict";
import { selectJobs, salaryLabel, jobStage } from "./board.js";
test("personal board combines search, stage, location and source without losing unfiled jobs", () => {
  const state = {
    jobs: [
      {
        id: "a",
        title: "Frontend разработчик",
        employer: { name: "Acme" },
        location: "Москва",
        source: "hh",
        remote: true,
      },
      { id: "b", title: "Backend", location: "Москва", source: "manual" },
    ],
    applications: [{ job_id: "a", stage: "saved" }],
  };
  assert.equal(
    selectJobs(state, {
      query: "ACME",
      stage: "saved",
      location: "Москва",
      source: "hh",
      remote: true,
    })[0].id,
    "a",
  );
  assert.equal(selectJobs(state, { query: "ACME", stage: "new" }).length, 0);
  assert.equal(selectJobs(state, { stage: "new" })[0].id, "b");
  assert.equal(jobStage(state.jobs[1], state.applications), "new");
});
test("missing and one-sided pay stay explicit", () => {
  assert.equal(salaryLabel({}), "Зарплата не указана");
  assert.match(
    salaryLabel({ salary_min: 100, currency: "EUR" }),
    /^от 100 EUR$/,
  );
  assert.match(salaryLabel({ salary_max: 200 }), /^до 200 валюта не указана$/);
});
