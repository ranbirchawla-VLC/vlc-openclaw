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
  const auth = await authorize();
  const gmail = google.gmail({ version: "v1", auth });

  const msg = await gmail.users.messages.get({
    userId: "me",
    id: "19d500138024894e",
    format: "full",
  });

  const payload = msg.data.payload;
  let body = "";

  function extractParts(parts) {
    if (!parts) return;
    for (const part of parts) {
      if (part.mimeType === "text/html" && part.body.data) {
        body += Buffer.from(part.body.data, "base64").toString("utf-8");
      } else if (part.mimeType === "text/plain" && part.body.data) {
        body += Buffer.from(part.body.data, "base64").toString("utf-8");
      }
      if (part.parts) extractParts(part.parts);
    }
  }

  if (payload.body && payload.body.data) {
    body = Buffer.from(payload.body.data, "base64").toString("utf-8");
  }
  extractParts(payload.parts);

  const links = [];
  const re = /href=["']([^"'<>]+)["']/gi;
  let m;
  while ((m = re.exec(body)) !== null) {
    links.push(m[1]);
  }

  console.log(JSON.stringify({ links, bodyLength: body.length }));
}

main().catch(e => console.error(e));
