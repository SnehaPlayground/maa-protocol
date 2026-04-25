#!/usr/bin/env python3
"""
Upload a file to Google Drive folder.
Uses Google API Python Client with OAuth2.
Credentials from gogcli config.
"""
import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# --- Configuration ---
DRIVE_FOLDER_ID = "1iwBp-J3Ke3ruJ7k57mOt8Z6eiwTkPY8H"
CREDENTIALS_FILE = "/root/.config/gogcli/credentials.json"
TOKEN_FILE = "/root/.openclaw/workspace/scripts/token_drive.json"
FILE_TO_UPLOAD = "/root/.openclaw/workspace/temp/whatsapp-management-pack.zip"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            with open(CREDENTIALS_FILE) as f:
                client_config = json.load(f)
            # gogcli stores as {"client_id":..., "client_secret":...}
            # Wrap for InstalledAppFlow which expects {"installed": {...}} or {"web": {...}}
            if "installed" not in client_config and "web" not in client_config:
                client_config = {"installed": client_config}
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds


def upload_file(filepath, folder_id):
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    filename = os.path.basename(filepath)
    file_metadata = {
        "name": filename,
        "parents": [folder_id],
    }
    media = MediaFileUpload(filepath, resumable=True)
    try:
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
        )
        result = request.execute()
        print(f"Uploaded: {result.get('name')}")
        print(f"File ID: {result.get('id')}")
        print(f"Link: {result.get('webViewLink')}")
        return result
    except HttpError as e:
        print(f"Upload failed: {e}")
        return None


if __name__ == "__main__":
    if not os.path.exists(FILE_TO_UPLOAD):
        print(f"File not found: {FILE_TO_UPLOAD}")
        exit(1)
    upload_file(FILE_TO_UPLOAD, DRIVE_FOLDER_ID)
