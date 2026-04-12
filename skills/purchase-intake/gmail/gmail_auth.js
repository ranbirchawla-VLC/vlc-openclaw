#!/usr/bin/env node
const fs = require("fs");
const path = require("path");
const { google } = require("googleapis");

const CREDENTIALS_PATH = path.join(__dirname, "credentials.json");
const TOKEN_PATH = path.join(__dirname, "token.json");

const code = process.argv[2];
if (!code) { console.error("Usage: node gmail_auth.js <code>"); process.exit(1); }

const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH));
const { client_id, client_secret, redirect_uris } = creds.installed;
const oAuth2Client = new google.auth.OAuth2(client_id, client_secret, redirect_uris[0]);

oAuth2Client.getToken(code, (err, token) => {
  if (err) { console.error("Error:", err.message); process.exit(1); }
  fs.writeFileSync(TOKEN_PATH, JSON.stringify(token));
  console.log("Token saved to", TOKEN_PATH);
});
