import json
import uasyncio as asyncio
import collections

from microdot_asyncio import Microdot, Request, Response, HTTPException

from ._static import assets
from .config import DOMAIN_LOCAL, DOMAIN_NAMES


Request.max_content_length = 1 << 30


def build_app(registry):
    app = Microdot()
    app.registry = registry

    @app.errorhandler(404)
    async def static(request):
        filename = request.path

        try:
            data = assets[filename]
        except KeyError:
            filename = filename.rstrip("/") + "/index.html"
            try:
                data = assets[filename]
            except KeyError:
                data = assets["/index.html"]

        headers = {}

        ext = filename.split(".")[-1]
        if ext in Response.types_map:
            headers["Content-Type"] = Response.types_map[ext]
        else:
            headers["Content-Type"] = "application/octet-stream"

        if filename.startswith("/assets/"):
            headers["Cache-Control"] = "public, max-age=604800, immutable"

        return data, 200, headers

    @app.get("/api/config")
    async def config_list(req):
        ret = collections.OrderedDict()
        for k in registry.config.keys():
            domain, value, key_info = registry.config.get(k)
            ret[k] = out = collections.OrderedDict()
            out["type"] = key_info.type_name
            if key_info.protected:
                out["protected"] = key_info.protected
            out["domain"] = DOMAIN_NAMES[domain]
            if not key_info.protected:
                out["value"] = value

        return json.dumps(ret), 200, {"Content-Type": "application/json"}

    @app.patch("/api/config")
    async def config_set(req):
        values = req.json

        if not isinstance(values, dict):
            raise HTTPException(400)

        try:
            registry.config.set(DOMAIN_LOCAL, values)
            return "{}", 201, {"Content-Type": "application/json"}

        except ValueError as exc:
            return (
                json.dumps({"error": str(exc)}),
                400,
                {"Content-Type": "application/json"},
            )

    return app
