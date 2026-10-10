// Delivery-alert Worker: POST /alert -> plain-text email through the
// Cloudflare Email Routing `send_email` binding.
//
// Config (all supplied at deploy time by cf-delivery-alert-deploy.sh; none
// of it lives in the repo):
//   ALERT_SECRET      secret_text  shared bearer secret
//   ALERT_RECIPIENTS  plain_text   comma-separated verified destination addrs
//   ALERT_FROM        plain_text   sender address on a zone with Email Routing
//   ALERT_EMAIL       send_email   binding (delivers to verified dests only)
//
// Request: POST /alert, "Authorization: Bearer <secret>", JSON body
//   {"kind": "<=64 chars", "message": "<=2000 chars"}
// Recipients are NEVER read from the request. Only kind + message are put
// in the mail body. Handler logic is exported (handleAlert) with an
// injectable `send` so it is unit-testable under `node --test`.

const MAX_KIND = 64;
const MAX_MESSAGE = 2000;
const MAX_BODY_BYTES = 8192;

const enc = new TextEncoder();

function text(status, body) {
  return new Response(body + "\n", {
    status,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

// Constant-time compare: hash both sides to equal-length digests, then
// XOR-accumulate every byte (no early exit, no length leak).
export async function secretsMatch(provided, expected) {
  if (!expected) return false; // unconfigured secret never authenticates
  const [a, b] = await Promise.all(
    [provided, expected].map(async (s) =>
      new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s))),
    ),
  );
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

// Strip CR/LF/control chars so a field can never inject headers.
const oneLine = (s) => s.replace(/[\x00-\x1f\x7f]+/g, " ").trim();

export function buildMime({ from, to, kind, message }) {
  const subject = `[delivery-alert] ${oneLine(kind)}`;
  const body = `kind: ${oneLine(kind)}\r\n\r\n${message.replace(/\r?\n/g, "\r\n")}\r\n`;
  return [
    `From: ${from}`,
    `To: ${to}`,
    `Subject: ${subject}`,
    `Date: ${new Date().toUTCString()}`,
    `Message-ID: <${crypto.randomUUID()}@alert.invalid>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=utf-8",
    "Content-Transfer-Encoding: 8bit",
    "",
    body,
  ].join("\r\n");
}

export async function handleAlert(request, env, send) {
  const url = new URL(request.url);
  if (url.pathname !== "/alert") return text(404, "not found");
  if (request.method !== "POST") return text(405, "method not allowed");

  const m = /^Bearer (.+)$/.exec(request.headers.get("Authorization") || "");
  if (!m || !(await secretsMatch(m[1], env.ALERT_SECRET))) {
    return text(401, "unauthorized");
  }

  const raw = await request.text();
  if (enc.encode(raw).length > MAX_BODY_BYTES) return text(400, "body too large");
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return text(400, "invalid json");
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return text(400, "expected a json object");
  }
  const { kind, message } = data;
  if (typeof kind !== "string" || kind.length < 1 || kind.length > MAX_KIND) {
    return text(400, "invalid kind");
  }
  if (typeof message !== "string" || message.length < 1 || message.length > MAX_MESSAGE) {
    return text(400, "invalid message");
  }

  const recipients = (env.ALERT_RECIPIENTS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (recipients.length === 0 || !env.ALERT_FROM) return text(500, "not configured");

  let failed = 0;
  for (const to of recipients) {
    try {
      await send({ from: env.ALERT_FROM, to, raw: buildMime({ from: env.ALERT_FROM, to, kind, message }) });
    } catch {
      failed++; // do not leak provider detail to the caller
    }
  }
  return failed ? text(502, `send failed for ${failed} of ${recipients.length}`) : text(200, "ok");
}

export default {
  async fetch(request, env) {
    // Dynamic import: `cloudflare:email` only exists in the Workers runtime.
    const { EmailMessage } = await import("cloudflare:email");
    const send = ({ from, to, raw }) => env.ALERT_EMAIL.send(new EmailMessage(from, to, raw));
    return handleAlert(request, env, send);
  },
};
