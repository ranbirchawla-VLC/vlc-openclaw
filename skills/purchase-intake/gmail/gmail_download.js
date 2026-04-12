#!/usr/bin/env node
/**
 * gmail_download.js — Download an attachment from Gmail to disk.
 *
 * Input (JSON on stdin):
 *   { "messageId": "...", "attachmentId": "...", "filename": "...", "outputDir": "..." }
 *
 * Output (JSON on stdout):
 *   { "ok": true, "path": "/full/path/to/file" }
 *   { "ok": false, "error": "..." }
 */

const fs = require("fs");
const path = require("path");
const { google } = require("googleapis");

const CREDENTIALS_PATH = path.join(__dirname, "credentials.json");
const TOKEN_PATH = path.join(__dirname, "token.json");

async function authorize() {
  const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH));
  const { client_id, client_secret, redirect_uris } = creds.installed;
  const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);
  oAuth2Client.setCredentials(JSON.parse(fs.readFileSync(TOKEN_PATH)));
  return oAuth2Client;
}

async function main() {
  let input = {};
  try {
    const raw = fs.readFileSync("/dev/stdin", "utf-8").trim();
    if (raw) input = JSON.parse(raw);
  } catch (e) {}

  const { messageId, attachmentId, filename, outputDir } = input;
  if (!messageId || !attachmentId || !filename || !outputDir) {
    console.log(JSON.stringify({ ok: false, error: "Missing required fields: messageId, attachmentId, filename, outputDir" }));
    return;
  }

  try {
    const auth = await authorize();
    const gmail = google.gmail({ version: "v1", auth });

    const res = await gmail.users.messages.attachments.get({
      userId: "me",
      messageId,
      id: attachmentId,
    });

    const data = Buffer.from(res.data.data, "base64");
    fs.mkdirSync(outputDir, { recursive: true });
    const outputPath = path.join(outputDir, filename);
    fs.writeFileSync(outputPath, data);

    console.log(JSON.stringify({ ok: true, path: outputPath }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: err.message }));
  }
}

main();
