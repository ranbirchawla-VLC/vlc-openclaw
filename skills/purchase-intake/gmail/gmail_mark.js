#!/usr/bin/env node
/**
 * gmail_mark.js — Mark an email as read and add a label.
 *
 * Input (JSON on stdin):
 *   { "messageId": "...", "addLabels": ["intake-complete"], "removeLabels": ["UNREAD"] }
 *
 * Output (JSON on stdout):
 *   { "ok": true }
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

  const { messageId, addLabels = [], removeLabels = ["UNREAD"] } = input;
  if (!messageId) {
    console.log(JSON.stringify({ ok: false, error: "Missing messageId" }));
    return;
  }

  try {
    const auth = await authorize();
    const gmail = google.gmail({ version: "v1", auth });

    await gmail.users.messages.modify({
      userId: "me",
      id: messageId,
      requestBody: {
        addLabelIds: addLabels,
        removeLabelIds: removeLabels,
      },
    });

    console.log(JSON.stringify({ ok: true }));
  } catch (err) {
    console.log(JSON.stringify({ ok: false, error: err.message }));
  }
}

main();
