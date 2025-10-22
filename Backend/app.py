import os
import uuid
import time
from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Dict, Any, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    # Use flask-smorest for OpenAPI/Swagger UI generation
    from flask_smorest import Api
except Exception:  # pragma: no cover
    Api = None  # Will raise at runtime if missing; requirements.txt updated accordingly


# App configuration
def create_app():
    """
    Factory to create and configure the Flask application with in-memory storage.
    Uses environment variables for future MongoDB integration but does not require them at runtime.

    OpenAPI/Swagger:
    - Interactive docs served at /api/docs
    - OpenAPI JSON served at /api/openapi.json
    """
    app = Flask(__name__)
    # Enable CORS for API routes; allow all origins in preview/dev
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # OpenAPI and Swagger UI config
    app.config["API_TITLE"] = "Device Management REST API"
    app.config["API_VERSION"] = "1.0.0"
    app.config["OPENAPI_VERSION"] = "3.0.3"
    # Serve docs under /api/docs and the JSON at /api/openapi.json
    app.config["OPENAPI_URL_PREFIX"] = "/api"
    app.config["OPENAPI_JSON_PATH"] = "openapi.json"
    app.config["OPENAPI_SWAGGER_UI_PATH"] = "docs"
    app.config["OPENAPI_SWAGGER_UI_URL"] = "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

    if Api is None:
        raise RuntimeError(
            "flask-smorest is required for OpenAPI docs. Please install dependencies."
        )
    api = Api(app)

    # Configuration via env (placeholders for future MongoDB integration)
    app.config["MONGODB_URL"] = os.getenv("MONGODB_URL", "")
    app.config["MONGODB_DB"] = os.getenv("MONGODB_DB", "")
    app.config["STATUS_CACHE_TTL_SECONDS"] = int(os.getenv("STATUS_CACHE_TTL_SECONDS", "10"))

    # In-memory storage for devices
    devices: Dict[str, Dict[str, Any]] = {}
    # Basic cache for device status
    status_cache: Dict[str, Dict[str, Any]] = {}

    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def validate_ip(ip: str) -> bool:
        try:
            ip_address(ip)
            return True
        except Exception:
            return False

    def has_duplicate_ip(ip: str, exclude_id: Optional[str] = None) -> bool:
        for did, d in devices.items():
            if exclude_id and did == exclude_id:
                continue
            if d.get("ip_address") == ip:
                return True
        return False

    def validate_device_payload(payload: Dict[str, Any], require_all: bool = True) -> (bool, Dict[str, str]):
        errors: Dict[str, str] = {}
        required_fields = ["name", "ip_address", "type", "location"]
        allowed_types = ["router", "switch", "server", "other"]
        # Required fields
        for field in required_fields:
            if require_all and not payload.get(field):
                errors[field] = f"{field} is required"
        # IP format
        if "ip_address" in payload:
            if not validate_ip(str(payload["ip_address"])):
                errors["ip_address"] = "Invalid IP address"
        # Type allowed
        if "type" in payload and payload["type"] not in allowed_types:
            errors["type"] = f"type must be one of {allowed_types}"
        return (len(errors) == 0), errors

    def cache_status(device_id: str, status: str, response_time_ms: Optional[int] = None):
        status_cache[device_id] = {
            "status": status,
            "last_checked": now_iso(),
            "response_time_ms": response_time_ms,
            "timestamp": time.time(),
        }

    def cached_status_valid(device_id: str) -> bool:
        ttl = app.config["STATUS_CACHE_TTL_SECONDS"]
        entry = status_cache.get(device_id)
        if not entry:
            return False
        return (time.time() - entry.get("timestamp", 0)) <= ttl

    def simulate_reachability(ip: str) -> (bool, Optional[int]):
        """
        Simulates reachability without external network dependencies.
        Simple heuristic:
        - If last octet of IPv4 is even => reachable
        - Otherwise unreachable
        - Response time randomized within a range to simulate latency
        """
        try:
            parts = ip.split(".")
            last = parts[-1]
            last_num = int("".join([c for c in last if c.isdigit()]) or "0")
            reachable = (last_num % 2 == 0)
            response_time_ms = 20 + (last_num % 50)  # pseudo-latency
            return reachable, response_time_ms if reachable else None
        except Exception:
            return False, None

    @app.route("/api/health", methods=["GET"])
    def health():
        """
        Health check route to verify backend is running.
        Returns 200 OK with simple JSON payload.
        """
        return jsonify({"status": "ok", "service": "device-backend", "time": now_iso()}), 200

    # PUBLIC_INTERFACE
    @app.route("/api/devices", methods=["GET"])
    def list_devices():
        """
        Get all devices with optional filtering and sorting.
        ---
        tags:
          - Devices
        parameters:
          - in: query
            name: type
            schema:
              type: string
            description: Filter by device type
          - in: query
            name: status
            schema:
              type: string
              enum: [online, offline, unknown]
            description: Filter by device status
          - in: query
            name: sort
            schema:
              type: string
            description: Sort by field (name, status, type, location)
        responses:
          200:
            description: List of devices
        Returns:
          - 200 JSON array of devices
        """
        devs: List[Dict[str, Any]] = list(devices.values())
        q_type = request.args.get("type")
        q_status = request.args.get("status")
        sort_field = request.args.get("sort")

        if q_type:
            devs = [d for d in devs if d.get("type") == q_type]
        if q_status:
            devs = [d for d in devs if d.get("status") == q_status]

        if sort_field:
            try:
                devs.sort(key=lambda x: str(x.get(sort_field, "")))
            except Exception:
                pass

        return jsonify(devs), 200

    # PUBLIC_INTERFACE
    @app.route("/api/devices", methods=["POST"])
    def create_device():
        """
        Create a new device.
        ---
        tags:
          - Devices
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required: [name, ip_address, type, location]
                properties:
                  name: {type: string}
                  ip_address: {type: string, format: ipv4}
                  type: {type: string, enum: [router, switch, server, other]}
                  location: {type: string}
        responses:
          201:
            description: Device created
          400:
            description: Invalid request
          409:
            description: Duplicate IP address
        """
        payload = request.get_json(silent=True) or {}
        ok, errors = validate_device_payload(payload, require_all=True)
        if not ok:
            return jsonify({"code": 400, "message": "Invalid request", "details": errors}), 400

        ip = payload["ip_address"]
        if has_duplicate_ip(ip):
            return jsonify({"code": 409, "message": "Duplicate IP address", "details": {"ip_address": "Duplicate"}}), 409

        did = str(uuid.uuid4())
        device = {
            "id": did,
            "name": payload["name"],
            "ip_address": ip,
            "type": payload["type"],
            "location": payload["location"],
            "status": "unknown",
            "last_checked": None,
        }
        devices[did] = device
        return jsonify(device), 201

    # PUBLIC_INTERFACE
    @app.route("/api/devices/<device_id>", methods=["GET"])
    def get_device(device_id: str):
        """
        Retrieve a specific device by ID.
        ---
        tags:
          - Devices
        parameters:
          - in: path
            name: device_id
            required: true
            schema:
              type: string
        responses:
          200:
            description: Device found
          404:
            description: Device not found
        Returns 200 with device JSON or 404 if not found.
        """
        device = devices.get(device_id)
        if not device:
            return jsonify({"code": 404, "message": "Device not found"}), 404
        return jsonify(device), 200

    # PUBLIC_INTERFACE
    @app.route("/api/devices/<device_id>", methods=["PUT"])
    def update_device(device_id: str):
        """
        Update an existing device.
        ---
        tags:
          - Devices
        parameters:
          - in: path
            name: device_id
            required: true
            schema:
              type: string
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required: [name, ip_address, type, location]
                properties:
                  name: {type: string}
                  ip_address: {type: string, format: ipv4}
                  type: {type: string, enum: [router, switch, server, other]}
                  location: {type: string}
        responses:
          200:
            description: Device updated
          400:
            description: Invalid request
          404:
            description: Device not found
          409:
            description: Duplicate IP
        """
        if device_id not in devices:
            return jsonify({"code": 404, "message": "Device not found"}), 404

        payload = request.get_json(silent=True) or {}
        ok, errors = validate_device_payload(payload, require_all=True)
        if not ok:
            return jsonify({"code": 400, "message": "Invalid request", "details": errors}), 400

        ip = payload["ip_address"]
        if has_duplicate_ip(ip, exclude_id=device_id):
            return jsonify({"code": 409, "message": "Duplicate IP address", "details": {"ip_address": "Duplicate"}}), 409

        # Update
        device = devices[device_id]
        device.update({
            "name": payload["name"],
            "ip_address": ip,
            "type": payload["type"],
            "location": payload["location"],
        })
        devices[device_id] = device
        # Invalidate status cache if IP changed
        status_cache.pop(device_id, None)
        return jsonify(device), 200

    # PUBLIC_INTERFACE
    @app.route("/api/devices/<device_id>", methods=["DELETE"])
    def delete_device(device_id: str):
        """
        Delete a device by ID.
        ---
        tags:
          - Devices
        parameters:
          - in: path
            name: device_id
            required: true
            schema:
              type: string
        responses:
          204:
            description: Deleted
          404:
            description: Not found
        """
        if device_id not in devices:
            return jsonify({"code": 404, "message": "Device not found"}), 404
        devices.pop(device_id, None)
        status_cache.pop(device_id, None)
        return ("", 204)

    # PUBLIC_INTERFACE
    @app.route("/api/devices/status", methods=["GET"])
    def get_all_status():
        """
        Retrieve statuses for all devices. Uses cached values where valid.
        ---
        tags:
          - Status
        responses:
          200:
            description: Array of statuses
        Returns 200 with array of {id, status, last_checked}
        """
        results: List[Dict[str, Any]] = []
        for did, d in devices.items():
            if cached_status_valid(did):
                c = status_cache[did]
                results.append({"id": did, "status": c["status"], "last_checked": c["last_checked"]})
            else:
                reachable, rtt = simulate_reachability(d["ip_address"])
                status = "online" if reachable else "offline"
                cache_status(did, status, rtt)
                d["status"] = status
                d["last_checked"] = status_cache[did]["last_checked"]
                results.append({"id": did, "status": status, "last_checked": d["last_checked"]})
        return jsonify(results), 200

    # PUBLIC_INTERFACE
    @app.route("/api/devices/<device_id>/status", methods=["POST"])
    def check_status(device_id: str):
        """
        Manually trigger status check (simulated ping) for a device.
        ---
        tags:
          - Status
        parameters:
          - in: path
            name: device_id
            required: true
            schema:
              type: string
        responses:
          200:
            description: Status check result
          404:
            description: Device not found
        Returns 200 with {id, status, last_checked}
        """
        device = devices.get(device_id)
        if not device:
            return jsonify({"code": 404, "message": "Device not found"}), 404

        reachable, rtt = simulate_reachability(device["ip_address"])
        status = "online" if reachable else "offline"
        cache_status(device_id, status, rtt)
        device["status"] = status
        device["last_checked"] = status_cache[device_id]["last_checked"]
        return jsonify({"id": device_id, "status": status, "last_checked": device["last_checked"]}), 200

    # The OpenAPI JSON is automatically available at /api/openapi.json and Swagger UI at /api/docs

    # Expose the Api instance on app for tooling (e.g., generate_openapi.py)
    app.extensions["smorest_api"] = api

    return app


app = create_app()

if __name__ == "__main__":
    # Use port 3001 for preview to match given environment
    port = int(os.getenv("PORT", "3001"))
    app.run(host="0.0.0.0", port=port)
