"""
MyanOS OneDrive Storage Module v1.0
For Render deployment - Flask storage API endpoints
"""

import os, json, time, requests
from functools import wraps

CLIENT_ID = os.environ.get("ONEDRIVE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ONEDRIVE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("ONEDRIVE_REFRESH_TOKEN", "")
ROOT_FOLDER = os.environ.get("ONEDRIVE_ROOT_FOLDER", "MyanOS")
TENANT = os.environ.get("ONEDRIVE_TENANT", "consumers")

TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
GRAPH_URL = "https://graph.microsoft.com/v1.0"
SCOPES = "Files.ReadWrite.All User.Read offline_access"

_access_token = ""
_token_expires = 0


def _get_access_token():
    """Get or refresh access token"""
    global _access_token, _token_expires, REFRESH_TOKEN
    
    if _access_token and time.time() < _token_expires - 60:
        return _access_token
    
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
        "scope": SCOPES
    }
    
    try:
        resp = requests.post(TOKEN_URL, data=data, timeout=30)
        result = resp.json()
        if "access_token" not in result:
            return None
        _access_token = result["access_token"]
        _token_expires = time.time() + result.get("expires_in", 3600)
        if "refresh_token" in result:
            REFRESH_TOKEN = result["refresh_token"]
        return _access_token
    except Exception:
        return None


def _graph_get(path):
    token = _get_access_token()
    if not token:
        return {"error": "Failed to authenticate"}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(f"{GRAPH_URL}{path}", headers=headers, timeout=30)
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _graph_put(path, data=None, content_type="application/json"):
    token = _get_access_token()
    if not token:
        return {"error": "Failed to authenticate"}
    headers = {"Authorization": f"Bearer {token}"}
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
    token = _get_access_token()
    if not token:
        return {"error": "Failed to authenticate"}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = requests.post(f"{GRAPH_URL}{path}", headers=headers, json=json_data, timeout=30)
        try:
            return resp.json()
        except Exception:
            return {"status": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def _graph_delete(path):
    token = _get_access_token()
    if not token:
        return {"error": "Failed to authenticate"}
    headers = {"Authorization": f"Bearer {token}"}
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


def register_storage_routes(app):
    """Register all storage API routes on Flask app"""
    
    @app.route("/api/storage/status", methods=["GET"])
    def storage_status():
        """Check OneDrive connection and quota"""
        data = _graph_get("/me/drive")
        if "error" in data:
            return {"connected": False, "error": data["error"]}, 503
        q = data["quota"]
        return {
            "connected": True,
            "account": data["owner"]["user"]["email"],
            "total_gb": round(q["total"] / (1024**3), 2),
            "used_gb": round(q["used"] / (1024**3), 2),
            "free_gb": round((q["total"] - q["used"]) / (1024**3), 2),
            "root_folder": ROOT_FOLDER
        }

    @app.route("/api/storage/onedrive/quota", methods=["GET"])
    def storage_quota():
        """Get OneDrive storage quota details"""
        data = _graph_get("/me/drive")
        if "error" in data:
            return {"error": data["error"]}, 503
        q = data["quota"]
        return {
            "account": data["owner"]["user"]["email"],
            "total": q["total"],
            "used": q["used"],
            "remaining": q["remaining"],
            "deleted": q["deleted"],
            "total_gb": round(q["total"] / (1024**3), 2),
            "used_gb": round(q["used"] / (1024**3), 2),
            "free_gb": round(q["remaining"] / (1024**3), 2)
        }

    @app.route("/api/storage/list", methods=["GET"])
    def storage_list():
        """List files in OneDrive folder"""
        path = request.args.get("path", "/")
        if path.startswith("/"):
            od_path = f"{ROOT_FOLDER}:{path}"
        else:
            od_path = f"{ROOT_FOLDER}/{path}"
        
        data = _graph_get(f"/me/drive/root:/{od_path}:/children")
        if "error" in data:
            return {"error": data["error"]}, 404
        
        items = []
        for item in data.get("value", []):
            items.append({
                "name": item["name"],
                "type": "folder" if "folder" in item else "file",
                "size": item.get("size", 0),
                "id": item["id"],
                "modified": item.get("lastModifiedDateTime", "")
            })
        return {"path": path, "items": items, "count": len(items)}

    @app.route("/api/storage/upload", methods=["POST"])
    def storage_upload():
        """Upload file to OneDrive"""
        if "file" not in request.files:
            return {"error": "No file provided"}, 400
        file = request.files["file"]
        remote_path = request.form.get("path", f"/{file.filename}")
        
        if remote_path.startswith("/"):
            od_path = f"{ROOT_FOLDER}:{remote_path}"
        else:
            od_path = f"{ROOT_FOLDER}/{remote_path}"
        
        file_data = file.read()
        headers = {"Authorization": f"Bearer {_get_access_token()}", "Content-Type": "application/octet-stream"}
        resp = requests.put(
            f"{GRAPH_URL}/me/drive/root:/{od_path}:/content",
            headers=headers, data=file_data, timeout=120
        )
        if resp.status_code in (200, 201):
            result = resp.json()
            return {"uploaded": result["name"], "size": result["size"], "id": result["id"]}
        return {"error": f"Upload failed: {resp.status_code}"}, 500

    @app.route("/api/storage/download/<path:filepath>", methods=["GET"])
    def storage_download(filepath):
        """Download file from OneDrive"""
        od_path = f"{ROOT_FOLDER}/{filepath}"
        headers = {"Authorization": f"Bearer {_get_access_token()}"}
        resp = requests.get(
            f"{GRAPH_URL}/me/drive/root:/{od_path}:/content",
            headers=headers, timeout=120, stream=True
        )
        if resp.status_code == 200:
            from flask import send_file
            import io
            return send_file(io.BytesIO(resp.content), as_attachment=True, 
                           download_name=os.path.basename(filepath))
        return {"error": "File not found"}, 404

    @app.route("/api/storage/delete", methods=["POST"])
    def storage_delete():
        """Delete file/folder from OneDrive"""
        data = request.get_json(force=True)
        path = data.get("path", "")
        if not path:
            return {"error": "path required"}, 400
        
        od_path = f"{ROOT_FOLDER}/{path.lstrip('/')}"
        result = _graph_delete(f"/me/drive/root:/{od_path}")
        if result.get("deleted"):
            return {"deleted": True, "path": path}
        return {"error": result.get("error", "Delete failed")}, 500

    @app.route("/api/storage/mkdir", methods=["POST"])
    def storage_mkdir():
        """Create folder in OneDrive"""
        data = request.get_json(force=True)
        name = data.get("name", "")
        if not name:
            return {"error": "name required"}, 400
        parent = data.get("parent", ROOT_FOLDER)
        
        result = _graph_post(f"/me/drive/root:/{parent}/children",
                           {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"})
        if "error" in result:
            return {"error": result["error"]}, 500
        return {"created": result["name"], "id": result["id"]}

    @app.route("/api/storage/sync", methods=["POST"])
    def storage_sync():
        """Sync status / trigger backup"""
        data = request.get_json(force=True) or {}
        action = data.get("action", "status")
        
        if action == "status":
            drive = _graph_get("/me/drive")
            if "error" in drive:
                return {"sync": False, "error": drive["error"]}, 503
            
            # Check MyanOS folder exists
            folder = _graph_get(f"/me/drive/root:/{ROOT_FOLDER}")
            if "error" in folder:
                return {"sync": False, "error": f"Folder '{ROOT_FOLDER}' not found"}, 404
            
            files = _graph_get(f"/me/drive/root:/{ROOT_FOLDER}:/children")
            item_count = len(files.get("value", []))
            
            return {
                "sync": True,
                "action": action,
                "account": drive["owner"]["user"]["email"],
                "folder": ROOT_FOLDER,
                "items": item_count,
                "used_gb": round(drive["quota"]["used"] / (1024**3), 2),
                "total_gb": round(drive["quota"]["total"] / (1024**3), 2)
            }
        
        return {"sync": True, "action": action, "message": "OK"}
