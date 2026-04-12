#!/usr/bin/env node
/**
 * gmail_check.js — Search Gmail for unread invoice emails.
 * Returns pre-classified, pre-parsed emails ready for field extraction.
 *
 * Input (JSON on stdin):
 *   { "query": "optional override" }
 *
 * Output (JSON on stdout):
 *   { "ok": true, "count": N, "emails": [...] }
 *
 * Each email includes:
 *   id, subject, from, date, type ("attachment"|"hosted_link"|"body_only"|"unknown")
 *   For type=attachment: attachments array with id/filename/mimeType
 *   For type=hosted_link: invoice_url (the direct invoice URL, already extracted)
 *   body_text: cleaned plain text of email body (HTML stripped)
 */

const fs = require("fs");
const path = require("path");
const { google } = require("googleapis");

const CREDENTIALS_PATH = path.join(__dirname, "credentials.json");
const TOKEN_PATH = path.join(__dirname, "token.json");

// Invoice-related MIME types
const INVOICE_MIME_TYPES = [
  "application/pdf",
  "image/jpeg", "image/jpg", "image/png",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel",
];

// Patterns that indicate a hosted invoice link
const INVOICE_LINK_PATTERNS = [
  /view.invoice/i, /invoice\.pdf/i, /\/invoice\//i, /\/invoices\//i,
  /view\/document/i, /billing\/invoice/i, /pay\..*invoice/i,
];

// Patterns to skip — not real invoices
const SKIP_PATTERNS = [
  /has been delivered/i, /your order.*shipped/i, /tracking number/i,
  /merchant statement/i, /monthly statement/i, /account statement/i,
  /password reset/i, /verify your email/i,
];

function stripHtml(html) {
  return html
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/\s{2,}/g, " ")
    .trim();
}

function extractUrls(text) {
  const urls = [];
  const regex = /https?:\/\/[^\s"'<>()[\]{}]+/gi;
  let match;
  while ((match = regex.exec(text)) !== null) {
    urls.push(match[0].replace(/[.,;:!?]+$/, ""));
  }
  return [...new Set(urls)];
}

function findInvoiceUrl(body, urls) {
  // Priority 1: URL matching invoice patterns
  for (const url of urls) {
    for (const pattern of INVOICE_LINK_PATTERNS) {
      if (pattern.test(url)) return url;
    }
  }
  // Priority 2: URL near "view invoice" text
  const invoiceTextMatch = body.match(/(?:view|open|download|see)\s+invoice[^<\n]{0,200}(https?:\/\/[^\s"'<>]+)/i);
  if (invoiceTextMatch) return invoiceTextMatch[1];
  // Priority 3: Any URL from known invoice platforms
  for (const url of urls) {
    if (/watchtrack\.com|invoice\.stripe\.com|app\.invoicely|freshbooks|quickbooks|wave\.com\/invoice|paypal\.com.*invoice/i.test(url)) {
      return url;
    }
  }
  return null;
}

async function authorize() {
  const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH));
  const { client_id, client_secret, redirect_uris } = creds.installed;
  const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);
  oAuth2Client.setCredentials(JSON.parse(fs.readFileSync(TOKEN_PATH)));
  return oAuth2Client;
}

async function processMessage(gmail, msgId) {
  const msg = await gmail.users.messages.get({
    userId: "me", id: msgId, format: "full",
  });

  const headers = {};
  for (const h of msg.data.payload.headers || []) {
    headers[h.name.toLowerCase()] = h.value;
  }

  const subject = headers.subject || "";
  const from = headers.from || "";
  const date = headers.date || "";

  // Skip non-invoice emails
  for (const pattern of SKIP_PATTERNS) {
    if (pattern.test(subject)) return null;
  }

  // Extract body and attachments
  let plainText = "";
  let htmlText = "";
  const attachments = [];

  function walkParts(parts) {
    if (!parts) return;
    for (const part of parts) {
      if (part.mimeType === "text/plain" && part.body?.data) {
        plainText += Buffer.from(part.body.data, "base64").toString("utf-8");
      } else if (part.mimeType === "text/html" && part.body?.data) {
        htmlText += Buffer.from(part.body.data, "base64").toString("utf-8");
      } else if (part.filename && part.body?.attachmentId) {
        if (INVOICE_MIME_TYPES.includes(part.mimeType)) {
          attachments.push({
            attachmentId: String(part.body.attachmentId), // full ID, never truncate
            filename: part.filename,
            mimeType: part.mimeType,
            messageId: msgId,
          });
        }
      }
      if (part.parts) walkParts(part.parts);
    }
  }

  if (msg.data.payload.body?.data) {
    const raw = Buffer.from(msg.data.payload.body.data, "base64").toString("utf-8");
    if (/<html/i.test(raw)) htmlText = raw; else plainText = raw;
  }
  walkParts(msg.data.payload.parts);

  const bodyText = plainText || stripHtml(htmlText);
  const allUrls = extractUrls(htmlText || plainText);
  const invoiceUrl = findInvoiceUrl(bodyText, allUrls);

  // Classify type
  let type = "unknown";
  if (attachments.length > 0) {
    type = "attachment";
  } else if (invoiceUrl) {
    type = "hosted_link";
  } else if (/invoice|total|amount due|payment/i.test(bodyText)) {
    type = "body_only";
  }

  if (type === "unknown") return null; // not an invoice email

  const result = {
    id: msgId,
    subject,
    from,
    date,
    snippet: msg.data.snippet || "",
    type,
    body_text: bodyText.substring(0, 3000),
  };

  if (type === "attachment") result.attachments = attachments;
  if (type === "hosted_link") {
    result.invoice_url = invoiceUrl;
    result.instruction = "Open invoice_url in browser. Do not parse body_text."
    delete result.body_text; // force agent to use invoice_url only
  }

  return result;
}

async function main() {
  let input = {};
  try {
    const raw = fs.readFileSync("/dev/stdin", "utf-8").trim();
    if (raw) input = JSON.parse(raw);
  } catch (e) {}

  const query = input.query ||
    "after:2026/04/01 (subject:invoice OR subject:receipt OR has:attachment filename:pdf OR \"your invoice\" OR \"view invoice\")";

  try {
    const auth = await authorize();
    const gmail = google.gmail({ version: "v1", auth });

    const res = await gmail.users.messages.list({ userId: "me", q: query, maxResults: 15 });
    const messages = res.data.messages || [];

    const emails = [];
    for (const msg of messages) {
      const email = await processMessage(gmail, msg.id);
      if (email) emails.push(email);
    }

    console.log(JSON.stringify({ ok: true, count: emails.length, emails }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: err.message }));
  }
}

main();
