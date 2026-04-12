#!/usr/bin/env node
/**
 * gmail_fetch_invoice.js — Fetch and extract full invoice content from an email.
 *
 * Handles all three invoice types automatically:
 *   - Type A (attachment): downloads PDF, extracts text via pdftotext
 *   - Type B (hosted link): opens URL in headless browser, extracts text or downloads PDF
 *   - Type C (body only): returns cleaned body text
 *
 * Input (JSON on stdin):
 *   {
 *     "email_id": "19d500138024894e",
 *     "type": "attachment" | "hosted_link" | "body_only",
 *     "invoice_url": "https://..." (required for hosted_link),
 *     "attachments": [...] (required for attachment type),
 *     "body_text": "..." (required for body_only type)
 *   }
 *
 * Output (JSON on stdout):
 *   {
 *     "ok": true,
 *     "email_id": "...",
 *     "type": "...",
 *     "invoice_text": "full extracted text",
 *     "source_url": "..." (for hosted_link),
 *     "local_path": "..." (for attachment, archived to Drive)
 *   }
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");
const { google } = require("googleapis");

const CREDENTIALS_PATH = path.join(__dirname, "credentials.json");
const TOKEN_PATH = path.join(__dirname, "token.json");
const TMP_DIR = "/tmp/vardalux-invoices";
const WORKSPACE_DIR = "/Users/ranbirchawla/.openclaw/workspace/skills/purchase-intake";
const DRIVE_INVOICES = "/Users/ranbirchawla/Library/CloudStorage/GoogleDrive-ranbir.chawla@rnvillc.com/Shared drives/Vardalux Ops Agent Data/VardaluxAgents/invoices";

function extractPdfText(filePath) {
  try {
    return execSync(`/opt/homebrew/bin/pdftotext "${filePath}" -`, {
      maxBuffer: 10 * 1024 * 1024,
    }).toString("utf-8").trim();
  } catch (e) {
    throw new Error(`pdftotext failed: ${e.message}`);
  }
}

async function authorize() {
  const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH));
  const { client_id, client_secret, redirect_uris } = creds.installed;
  const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);
  oAuth2Client.setCredentials(JSON.parse(fs.readFileSync(TOKEN_PATH)));
  return oAuth2Client;
}

async function handleAttachment(auth, emailId, attachments) {
  const gmail = google.gmail({ version: "v1", auth });
  fs.mkdirSync(TMP_DIR, { recursive: true });
  fs.mkdirSync(DRIVE_INVOICES, { recursive: true });

  // Use first PDF attachment, fall back to first image
  const att = attachments.find(a => a.mimeType === "application/pdf")
    || attachments.find(a => a.mimeType.startsWith("image/"))
    || attachments[0];

  if (!att) throw new Error("No usable attachment found");

  // Download attachment
  const res = await gmail.users.messages.attachments.get({
    userId: "me",
    messageId: att.messageId || emailId,
    id: att.attachmentId,
  });

  const data = Buffer.from(res.data.data, "base64");
  const safeFilename = `${emailId}-${att.filename.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
  const tmpPath = path.join(TMP_DIR, safeFilename);
  const archivePath = path.join(DRIVE_INVOICES, safeFilename);

  fs.writeFileSync(tmpPath, data);

  // Extract text
  let invoiceText = "";
  if (att.mimeType === "application/pdf") {
    invoiceText = extractPdfText(tmpPath);
  } else {
    // Image — return path for agent to use image tool
    fs.copyFileSync(tmpPath, archivePath);
    return {
      ok: true,
      email_id: emailId,
      type: "attachment_image",
      invoice_text: null,
      local_path: tmpPath,
      archive_path: archivePath,
      note: "Image attachment — use image tool on local_path to extract text",
    };
  }

  // Archive to Drive
  try { fs.copyFileSync(tmpPath, archivePath); } catch(e) {}

  return {
    ok: true,
    email_id: emailId,
    type: "attachment",
    invoice_text: invoiceText,
    local_path: tmpPath,
    archive_path: archivePath,
  };
}

async function handleHostedLink(emailId, invoiceUrl) {
  // Use Playwright/puppeteer if available, otherwise use curl to get page text
  // Try curl first (works for simple pages like WatchTrack invoices)
  try {
    const html = execSync(
      `curl -sL --max-time 15 --user-agent "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" "${invoiceUrl}"`,
      { maxBuffer: 5 * 1024 * 1024 }
    ).toString("utf-8");

    // Check if we got a real page
    if (html.length < 500 || /login|sign.in|authenticate/i.test(html.substring(0, 2000))) {
      return {
        ok: true,
        email_id: emailId,
        type: "hosted_link",
        invoice_text: null,
        source_url: invoiceUrl,
        note: "Page requires login or returned empty. Use browser tool to open: " + invoiceUrl,
        browser_required: true,
      };
    }

    // Strip HTML to get text
    const text = html
      .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
      .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/\s{2,}/g, " ")
      .trim();

    if (text.length < 200) {
      return {
        ok: true,
        email_id: emailId,
        type: "hosted_link",
        invoice_text: null,
        source_url: invoiceUrl,
        note: "Page content too short — likely requires JavaScript. Use browser tool to open: " + invoiceUrl,
        browser_required: true,
      };
    }

    return {
      ok: true,
      email_id: emailId,
      type: "hosted_link",
      invoice_text: text.substring(0, 8000),
      source_url: invoiceUrl,
    };
  } catch (e) {
    return {
      ok: true,
      email_id: emailId,
      type: "hosted_link",
      invoice_text: null,
      source_url: invoiceUrl,
      note: "curl failed. Use browser tool to open: " + invoiceUrl,
      browser_required: true,
    };
  }
}

async function main() {
  let input = {};
  try {
    const raw = fs.readFileSync("/dev/stdin", "utf-8").trim();
    if (raw) input = JSON.parse(raw);
  } catch (e) {}

  const { email_id, type, invoice_url, attachments, body_text } = input;

  if (!email_id) {
    console.log(JSON.stringify({ ok: false, error: "Missing email_id" }));
    return;
  }

  try {
    let result;

    if (type === "attachment") {
      if (!attachments || attachments.length === 0) {
        console.log(JSON.stringify({ ok: false, error: "No attachments provided" }));
        return;
      }
      const auth = await authorize();
      result = await handleAttachment(auth, email_id, attachments);

    } else if (type === "hosted_link") {
      if (!invoice_url) {
        console.log(JSON.stringify({ ok: false, error: "No invoice_url provided" }));
        return;
      }
      result = await handleHostedLink(email_id, invoice_url);

    } else if (type === "body_only") {
      result = {
        ok: true,
        email_id,
        type: "body_only",
        invoice_text: body_text || "",
      };

    } else {
      console.log(JSON.stringify({ ok: false, error: `Unknown type: ${type}` }));
      return;
    }

    console.log(JSON.stringify(result));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: err.message }));
  }
}

main();
