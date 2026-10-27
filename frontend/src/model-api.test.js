import test from "node:test";
import assert from "node:assert/strict";
import { modelRequest, connectionPayload } from "./model-api.js";

test("connection payload validates required fields and sends a new key only when entered", () => {
  assert.deepEqual(connectionPayload({ base_url: " http://localhost:1234/v1/ ", model: " local-model ", api_key: "", persist: false }), { base_url: "http://localhost:1234/v1", model: "local-model", persist: false });
  assert.equal(connectionPayload({ base_url: "https://api.example.org/v1", model: "demo", api_key: " demo-key ", persist: true }).api_key, "demo-key");
  assert.throws(() => connectionPayload({ base_url: "", model: "demo" }), /адрес/i);
  assert.throws(() => connectionPayload({ base_url: "https://api.example.org/v1", model: "" }), /модель/i);
  assert.throws(() => connectionPayload({ base_url: "file:///tmp", model: "demo" }), /http/i);
});

test("model API requests stay local, use the client header, and do not cache credentials", async () => {
  const calls = [];
  const fakeFetch = async (path, options) => {
    calls.push({ path, options });
    return { ok: true, json: async () => path.endsWith("/models") ? { ok: true, result: ["demo"] } : { base_url: "http://localhost:1234/v1", has_key: false } };
  };
  const status = await modelRequest("", undefined, fakeFetch);
  assert.equal(status.has_key, false);
  assert.deepEqual(await modelRequest("/models", { base_url: "http://localhost:1234/v1" }, fakeFetch), ["demo"]);
  assert.equal(calls[0].path, "/api/model");
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[1].options.headers["X-Worklife-Client"], "local");
  assert.equal(calls[1].options.cache, "no-store");
  assert.ok(!calls[0].options.body);
});

test("model connection failures remain errors rather than a readiness claim", async () => {
  await assert.rejects(modelRequest("", {}, async () => ({ ok: false, json: async () => ({ ok: false, error: "Не удалось подключиться" }) })), /Не удалось подключиться/);
  await assert.rejects(modelRequest("", {}, async () => ({ ok: false, json: async () => { throw new Error("bad json"); } })), /ответ/i);
});
