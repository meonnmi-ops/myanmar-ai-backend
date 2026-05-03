#!/usr/bin/env python3
"""
MyanOS OneDrive Helper CLI v1.1
For Termux - Direct OneDrive API access (no server needed)

Usage:
  python3 onedrive_helper.py init          # First-time setup (create config)
  python3 onedrive_helper.py quota
  python3 onedrive_helper.py list [path]
  python3 onedrive_helper.py download <remote> [local]
  python3 onedrive_helper.py upload <local> [remote]
  python3 onedrive_helper.py delete <remote>
  python3 onedrive_helper.py mkdir <name>
  python3 onedrive_helper.py info <remote>
"""

import os, sys, json, requests

CONFIG_DIR = os.path.expanduser("~/.myanos")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = "Files.ReadWrite.All User.Read offline_access"

access_token = ""
config = {}


def _load_config():
    """Load config from file"""
    global config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
        except Exception:
            config = {}
    if not config.get("client_id"):
        print("ERROR: Config not found. Run: python3 onedrive_helper.py init")
        print("  This will create ~/.myanos/config.json")
        sys.exit(1)


def _save_config():
    """Save config to file"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def _init_config():
    """Interactive config setup"""
    print("=== MyanOS OneDrive Setup ===")
    print()
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            existing = json.load(f)
        print(f"Config exists: {CONFIG_FILE}")
        print(f"  Account: {existing.get('email', 'N/A')}")
        print(f"  Client ID: {existing.get('client_id', 'N/A')[:20]}...")
        choice = input("Overwrite? (y/N): ").strip().lower()
        if choice != "y":
            print("Cancelled.")
            return
    
    client_id = input("Client ID [88672fdd-4f3e-451c-89de-af3beba86b5e]: ").strip() or "88672fdd-4f3e-451c-89de-af3beba86b5e"
    
    client_secret = input("Client Secret: ").strip()
    if not client_secret:
        print("Client Secret is required!")
        sys.exit(1)
    
    refresh_token = input("Refresh Token: ").strip()
    if not refresh_token:
        print("Refresh Token is required!")
        sys.exit(1)
    
    tenant = input("Tenant [consumers]: ").strip() or "consumers"
    root_folder = input("Root Folder [MyanOS]: ").strip() or "MyanOS"
    
    config = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "tenant": tenant,
        "root_folder": root_folder
    }
    
    _save_config()
    
    # Verify
    print("\nVerifying connection...")
    refresh_access_token()
    
    data = _graph_get("/me/drive")
    if "error" in data:
        print(f"Verification FAILED: {data['error']['message']}")
        os.remove(CONFIG_FILE)
        print("Config removed. Please check credentials and try again.")
    else:
        q = data["quota"]
        email = data["owner"]["user"]["email"]
        total_gb = q["total"] / (1024**3)
        used_gb = q["used"] / (1024**3)
        config["email"] = email
        _save_config()
        print(f"\n✅ Connected to {email}")
        print(f"   Storage: {used_gb:.1f} GB / {total_gb:.0f} GB")
        print(f"   Config saved to: {CONFIG_FILE}")


def refresh_access_token():
    """Get new access token using refresh token"""
    global access_token, config
    data = {
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "refresh_token": config["refresh_token"],
        "grant_type": "refresh_token",
        "scope": SCOPES
    }
    try:
        resp = requests.post(
            TOKEN_URL.format(tenant=config["tenant"]),
            data=data, timeout=30
        )
        result = resp.json()
        if "access_token" not in result:
            print(f"Token error: {result.get('error_description', result.get('error', 'unknown'))}")
            sys.exit(1)
        access_token = result["access_token"]
        if "refresh_token" in result:
            config["refresh_token"] = result["refresh_token"]
            _save_config()
        return access_token
    except Exception as e:
        print(f"Network error: {e}")
        sys.exit(1)


def _graph_get(path):
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.get(f"{GRAPH_URL}{path}", headers=headers, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _graph_put(path, data=None, content_type="application/json"):
    headers = {"Authorization": f"Bearer {access_token}"}
    if content_type:
        headers["Content-Type"] = content_type
    try:
        resp = requests.put(f"{GRAPH_URL}{path}", headers=headers, data=data, timeout=120)
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def _graph_post(path, json_data=None):
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        resp = requests.post(f"{GRAPH_URL}{path}", headers=headers, json=json_data, timeout=30)
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def _graph_delete(path):
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        resp = requests.delete(f"{GRAPH_URL}{path}", headers=headers, timeout=30)
        if resp.status_code == 204:
            return {"deleted": True}
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def _resolve_path(path):
    """Build OneDrive path relative to root folder"""
    root = config.get("root_folder", "MyanOS")
    if path.startswith("/"):
        return f"{root}:{path}"
    return f"{root}/{path}"


def cmd_quota():
    data = _graph_get("/me/drive")
    if "error" in data:
        print(f"Error: {data['error']['message']}")
        return
    q = data["quota"]
    used = q["used"]
    total = q["total"]
    used_gb = used / (1024**3)
    total_gb = total / (1024**3)
    free_gb = (total - used) / (1024**3)
    pct = (used / total) * 100
    print(f"Account: {data['owner']['user']['email']}")
    print(f"Total:   {total_gb:.2f} GB")
    print(f"Used:    {used_gb:.2f} GB ({pct:.1f}%)")
    print(f"Free:    {free_gb:.2f} GB")


def cmd_list(path=None):
    root = config.get("root_folder", "MyanOS")
    if path:
        api_path = f"/me/drive/root:/{_resolve_path(path)}:/children"
    else:
        api_path = f"/me/drive/root:/{root}:/children"
    
    data = _graph_get(api_path)
    if "error" in data:
        print(f"Error: {data['error']['message']}")
        return
    
    items = data.get("value", [])
    if not items:
        print("(empty)")
        return
    
    for item in items:
        name = item["name"]
        size = item.get("size", 0)
        modified = item.get("lastModifiedDateTime", "")[:19].replace("T", " ")
        if "folder" in item:
            print(f"  DIR  {name}/   ({modified})")
        else:
            if size >= 1024*1024:
                s = f"{size/(1024*1024):.1f} MB"
            elif size >= 1024:
                s = f"{size/1024:.1f} KB"
            else:
                s = f"{size} B"
            print(f"  FILE {name}   {s:>10}   ({modified})")


def cmd_download(remote_path, local_path="."):
    od_path = _resolve_path(remote_path)
    headers = {"Authorization": f"Bearer {access_token}"}
    print(f"Downloading: {remote_path}")
    resp = requests.get(
        f"{GRAPH_URL}/me/drive/root:/{od_path}:/content",
        headers=headers, timeout=120, stream=True
    )
    if resp.status_code == 200:
        fname = os.path.basename(remote_path)
        if os.path.isdir(local_path):
            local_path = os.path.join(local_path, fname)
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = (downloaded / total) * 100
                    bar = "=" * int(pct / 2) + ">" + " " * (50 - int(pct / 2))
                    sys.stdout.write(f"\r  [{bar}] {pct:.0f}%")
                    sys.stdout.flush()
        print(f"\nSaved: {local_path} ({downloaded} bytes)")
    else:
        print(f"Error: {resp.status_code} - {resp.text[:200]}")


def cmd_upload(local_path, remote_path=None):
    if not os.path.exists(local_path):
        print(f"File not found: {local_path}")
        return
    fname = os.path.basename(local_path)
    if remote_path is None:
        remote_path = f"/{fname}"
    od_path = _resolve_path(remote_path)
    size = os.path.getsize(local_path)

    print(f"Uploading: {local_path} ({size} bytes)")
    with open(local_path, "rb") as f:
        file_data = f.read()
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"}
    resp = requests.put(
        f"{GRAPH_URL}/me/drive/root:/{od_path}:/content",
        headers=headers, data=file_data, timeout=120
    )
    if resp.status_code in (200, 201):
        result = resp.json()
        print(f"Uploaded: {result['name']} ({result['size']} bytes)")
    else:
        print(f"Error: {resp.status_code} - {resp.text[:200]}")


def cmd_delete(remote_path):
    od_path = _resolve_path(remote_path)
    print(f"Deleting: {remote_path}")
    result = _graph_delete(f"/me/drive/root:/{od_path}")
    if result.get("deleted"):
        print("Deleted successfully")
    elif "error" in result:
        print(f"Error: {result['error']['message']}")
    else:
        print(f"Result: {result}")


def cmd_mkdir(folder_name):
    root = config.get("root_folder", "MyanOS")
    print(f"Creating folder: {folder_name}")
    result = _graph_post(
        f"/me/drive/root:/{root}/children",
        {"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
    )
    if "error" in result:
        print(f"Error: {result['error']['message']}")
    else:
        print(f"Created: {result['name']}")


def cmd_info(remote_path):
    od_path = _resolve_path(remote_path)
    data = _graph_get(f"/me/drive/root:/{od_path}")
    if "error" in data:
        print(f"Error: {data['error']['message']}")
        return
    print(f"Name:     {data['name']}")
    print(f"Size:     {data.get('size', 0)} bytes")
    print(f"Created:  {data.get('createdDateTime', 'N/A')[:19].replace('T', ' ')}")
    print(f"Modified: {data.get('lastModifiedDateTime', 'N/A')[:19].replace('T', ' ')}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "init":
        _init_config()
        return

    _load_config()

    print("MyanOS OneDrive Helper v1.1")
    print(f"Authenticating...")
    refresh_access_token()
    print("OK\n")

    if cmd == "quota":
        cmd_quota()
    elif cmd == "list":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_list(path)
    elif cmd == "download":
        if len(sys.argv) < 3:
            print("Usage: onedrive_helper.py download <remote> [local]")
            sys.exit(1)
        cmd_download(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ".")
    elif cmd == "upload":
        if len(sys.argv) < 3:
            print("Usage: onedrive_helper.py upload <local> [remote]")
            sys.exit(1)
        cmd_upload(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: onedrive_helper.py delete <remote>")
            sys.exit(1)
        cmd_delete(sys.argv[2])
    elif cmd == "mkdir":
        if len(sys.argv) < 3:
            print("Usage: onedrive_helper.py mkdir <name>")
            sys.exit(1)
        cmd_mkdir(sys.argv[2])
    elif cmd == "info":
        if len(sys.argv) < 3:
            print("Usage: onedrive_helper.py info <remote>")
            sys.exit(1)
        cmd_info(sys.argv[2])
    else:
        print(f"Unknown: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
