import json
import uasyncio as asyncio
import collections

from microdot_asyncio import Microdot, Request, Response, HTTPException
from microdot_asyncio_websocket import with_websocket

from ._static import assets
from .config import DOMAIN_LOCAL, DOMAIN_NAMES
from ribbit.utils.time import isotime


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
    
    @app.route("/api/sensors")
    @with_websocket
    async def sensor_status(request, ws):
        while True:
            await asyncio.sleep_ms(1000)
            ret = collections.OrderedDict()
            for sensor in registry.sensors.values():
                if sensor.config.name == "dps310":
                    ret[sensor.config.name] = {
                        "temperature": sensor.temperature,
                        "pressure": sensor.pressure,
                        "t": isotime(sensor.last_update),
                    }
                elif sensor.config.name == "scd30":
                    ret[sensor.config.name] = {
                        "temperature": sensor.temperature,
                        "co2": sensor.co2,
                        "humidity": sensor.humidity,
                        "t": isotime(sensor.last_update),
                    }
                elif sensor.config.name == "gps":
                    ret[sensor.config.name] = {
                        "has_fix": sensor.has_fix,
                        "latitude": sensor.latitude,
                        "longitude": sensor.longitude,
                        "altitude": sensor.altitude,
                        "t": isotime(sensor.last_update),
                    }

            await ws.send(json.dumps(ret))

    @app.route("/api/config")
    def registry_list(request):
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
            registry.config.set(values)
            return "{}", 201, {"Content-Type": "application/json"}

        except ValueError as exc:
            return (
                json.dumps({"error": str(exc)}),
                400,
                {"Content-Type": "application/json"},
            )

    return app
