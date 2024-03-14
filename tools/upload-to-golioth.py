import base64
import json
import os

import requests


def load_version():
    with open("__version__.py") as f:
        data = f.read()

    ret = {}
    exec(data, None, ret)
    return ret


version_data = load_version()

session = requests.Session()
session.headers["x-api-key"] = os.environ["GOLIOTH_API_KEY"]

project = os.environ["GOLIOTH_PROJECT"]
blueprint = os.environ["GOLIOTH_BLUEPRINT"]
rollout = os.environ.get("GOLIOTH_ROLLOUT", "false")


req = {
    "blueprintId": blueprint,
    "package": "main",
    "projectId": project,
    "version": version_data["version"],
}

with open("firmware/micropython.bin", "rb") as f:
    req["content"] = base64.b64encode(f.read()).decode("ascii")

r = session.post(
    "https://api.golioth.io/v1/artifacts",
    data=json.dumps(req),
    headers={
        "Content-Type": "application/json",
    },
)
r.raise_for_status()
artifact = r.json()

r = session.post(
    "https://api.golioth.io/v1/projects/%s/releases" % (project,),
    data=json.dumps(
        {
            "blueprintId": blueprint,
            "artifactIds": [
                artifact["data"]["id"],
            ],
            "rollout":rollout
        }
    ),
    headers={
        "Content-Type": "application/json",
    },
)
r.raise_for_status()
