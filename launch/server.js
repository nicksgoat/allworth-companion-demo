// Allworth Companion — launch page server.
//
// Zero dependencies (Node built-ins only) so it runs on an Azure Web App with no
// `npm install` step. Two jobs: (1) a shared-password gate via HTTP Basic Auth,
// (2) static serving of ./public.
//
// Config (set as Azure App Settings):
//   SITE_USER      shared username   (default: "allworth")
//   SITE_PASSWORD  shared password   (default below — OVERRIDE in production)
//   PORT           injected by Azure (default: 8080 locally)

"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = process.env.PORT || 8080;
const PUBLIC_DIR = path.join(__dirname, "public");

const SITE_USER = process.env.SITE_USER || "allworth";
// Local/default password. Override with the SITE_PASSWORD App Setting on Azure.
const SITE_PASSWORD = process.env.SITE_PASSWORD || "ally-for-life";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".map": "application/json; charset=utf-8",
};

// Constant-time string compare so the gate can't be timed.
function safeEqual(a, b) {
  const ab = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ab.length !== bb.length) {
    // Still run a comparison to keep timing flat.
    crypto.timingSafeEqual(ab, ab);
    return false;
  }
  return crypto.timingSafeEqual(ab, bb);
}

function isAuthorized(req) {
  const header = req.headers.authorization || "";
  if (!header.startsWith("Basic ")) return false;
  let decoded;
  try {
    decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
  } catch (_) {
    return false;
  }
  const sep = decoded.indexOf(":");
  if (sep === -1) return false;
  const user = decoded.slice(0, sep);
  const pass = decoded.slice(sep + 1);
  // Evaluate both halves regardless, then AND — avoids short-circuit timing leak.
  const okUser = safeEqual(user, SITE_USER);
  const okPass = safeEqual(pass, SITE_PASSWORD);
  return okUser && okPass;
}

function sendAuthChallenge(res) {
  res.writeHead(401, {
    "WWW-Authenticate": 'Basic realm="Allworth Companion", charset="UTF-8"',
    "Content-Type": "text/html; charset=utf-8",
  });
  res.end(
    "<!doctype html><meta charset=utf-8><title>Allworth Companion</title>" +
      "<body style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0C2E4E;color:#fff;display:grid;place-items:center;height:100vh;margin:0\">" +
      "<p style=\"opacity:.7\">Authentication required.</p></body>"
  );
}

// Resolve a request path to a real file inside PUBLIC_DIR, blocking traversal.
function resolveFile(urlPath) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(urlPath, "http://x").pathname);
  } catch (_) {
    return null;
  }
  if (pathname === "/" || pathname === "") pathname = "/index.html";
  // Normalize and confine to PUBLIC_DIR.
  const filePath = path.join(PUBLIC_DIR, path.normalize(pathname));
  if (!filePath.startsWith(PUBLIC_DIR)) return null;
  return filePath;
}

function serveStatic(req, res) {
  const filePath = resolveFile(req.url);
  if (!filePath) {
    res.writeHead(400);
    return res.end("Bad request");
  }
  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      // A missing asset (has a file extension) is a real 404 — so a broken <img>
      // triggers its onerror placeholder instead of decoding the HTML shell.
      if (path.extname(filePath)) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        return res.end("Not found");
      }
      // Otherwise it's a client route → serve the SPA shell so deep links resolve.
      const shell = path.join(PUBLIC_DIR, "index.html");
      return fs.readFile(shell, (e2, buf) => {
        if (e2) {
          res.writeHead(404, { "Content-Type": "text/plain" });
          return res.end("Not found");
        }
        res.writeHead(200, { "Content-Type": MIME[".html"] });
        res.end(buf);
      });
    }
    const ext = path.extname(filePath).toLowerCase();
    const type = MIME[ext] || "application/octet-stream";
    // index.html must never be cached; fingerprint-free assets get a short cache.
    const cache =
      ext === ".html"
        ? "no-cache"
        : ext === ".png" || ext === ".jpg" || ext === ".jpeg" || ext === ".webp" || ext === ".svg"
          ? "public, max-age=86400"
          : "public, max-age=3600";
    res.writeHead(200, { "Content-Type": type, "Cache-Control": cache });
    fs.createReadStream(filePath).pipe(res);
  });
}

const server = http.createServer((req, res) => {
  if (!isAuthorized(req)) return sendAuthChallenge(res);
  if (req.method !== "GET" && req.method !== "HEAD") {
    res.writeHead(405, { Allow: "GET, HEAD" });
    return res.end("Method not allowed");
  }
  serveStatic(req, res);
});

server.listen(PORT, () => {
  // eslint-disable-next-line no-console
  console.log(`Allworth Companion launch page on :${PORT}`);
});
