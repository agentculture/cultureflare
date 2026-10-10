import { test } from "node:test";
import assert from "node:assert/strict";
import { handleAlert, buildMime } from "../../.claude/skills/cultureflare-write/templates/delivery-alert.js";

const SECRET = "s3cret-value";
const env = (over = {}) => ({
  ALERT_SECRET: SECRET,
  ALERT_FROM: "alerts@example.test",
  ALERT_RECIPIENTS: "a@example.test, b@example.test",
  ALERT_EMAIL: {},
  ...over,
});
const req = (body, { auth = `Bearer ${SECRET}`, method = "POST", path = "/alert" } = {}) =>
  new Request(`https://w.test${path}`, {
    method,
    headers: auth === null ? {} : { Authorization: auth },
    body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
  });
const run = async (r, e = env()) => {
  const sent = [];
  const res = await handleAlert(r, e, async (m) => sent.push(m));
  return { res, sent };
};

test("missing secret -> 401, no sends", async () => {
  const { res, sent } = await run(req({ kind: "k", message: "m" }, { auth: null }));
  assert.equal(res.status, 401);
  assert.equal(sent.length, 0);
});

test("wrong secret -> 401, no sends", async () => {
  for (const a of ["Bearer nope", "Bearer " + SECRET + "x", SECRET, "Basic " + SECRET, "Bearer "]) {
    const { res, sent } = await run(req({ kind: "k", message: "m" }, { auth: a }));
    assert.equal(res.status, 401, a);
    assert.equal(sent.length, 0);
  }
});

test("unconfigured secret never authenticates", async () => {
  const { res, sent } = await run(req({ kind: "k", message: "m" }, { auth: "Bearer " }), env({ ALERT_SECRET: "" }));
  assert.equal(res.status, 401);
  assert.equal(sent.length, 0);
});

test("good secret -> one send per recipient, body only kind+message", async () => {
  const { res, sent } = await run(
    req({ kind: "resend_failure", message: "provider down", extra: "guest@x.test 123456" }),
  );
  assert.equal(res.status, 200);
  assert.equal(sent.length, 2);
  assert.deepEqual(sent.map((m) => m.to), ["a@example.test", "b@example.test"]);
  for (const m of sent) {
    assert.equal(m.from, "alerts@example.test");
    assert.ok(m.raw.includes("resend_failure"));
    assert.ok(m.raw.includes("provider down"));
    assert.ok(!m.raw.includes("guest@x.test"));
    assert.ok(!m.raw.includes("123456"));
    assert.ok(m.raw.includes("Content-Type: text/plain; charset=utf-8"));
  }
});

test("recipients never come from the request", async () => {
  const { sent } = await run(req({ kind: "k", message: "m", to: "evil@x.test", recipients: ["evil@x.test"] }));
  assert.ok(sent.every((m) => !m.raw.includes("evil@x.test") && m.to !== "evil@x.test"));
});

test("header injection in kind is neutralised", () => {
  const raw = buildMime({ from: "f@example.test", to: "t@example.test", kind: "x\r\nBcc: e@x.test", message: "m" });
  assert.ok(!/^Bcc:/m.test(raw));
});

test("bad input -> 400, no sends", async () => {
  const cases = [
    "not json",
    "[]",
    "null",
    { kind: "k" },
    { message: "m" },
    { kind: 1, message: "m" },
    { kind: "", message: "m" },
    { kind: "k".repeat(65), message: "m" },
    { kind: "k", message: "m".repeat(2001) },
  ];
  for (const c of cases) {
    const { res, sent } = await run(req(c));
    assert.equal(res.status, 400, JSON.stringify(c).slice(0, 40));
    assert.equal(sent.length, 0);
  }
});

test("max-length fields accepted", async () => {
  const { res, sent } = await run(req({ kind: "k".repeat(64), message: "m".repeat(2000) }));
  assert.equal(res.status, 200);
  assert.equal(sent.length, 2);
});

test("oversize raw body -> 400 before parse", async () => {
  const { res, sent } = await run(req("x".repeat(10000)));
  assert.equal(res.status, 400);
  assert.equal(sent.length, 0);
});

test("no recipients configured -> 500, no sends", async () => {
  const { res, sent } = await run(req({ kind: "k", message: "m" }), env({ ALERT_RECIPIENTS: " , " }));
  assert.equal(res.status, 500);
  assert.equal(sent.length, 0);
});

test("routing: other path 404, non-POST 405 (auth checked first for POST only)", async () => {
  assert.equal((await run(req({}, { path: "/other" }))).res.status, 404);
  assert.equal((await run(req(null, { method: "GET" }))).res.status, 405);
});

test("send failure -> 502 without leaking detail", async () => {
  const res = await handleAlert(req({ kind: "k", message: "m" }), env(), async () => {
    throw new Error("boom internal");
  });
  assert.equal(res.status, 502);
  assert.ok(!(await res.text()).includes("boom"));
});
