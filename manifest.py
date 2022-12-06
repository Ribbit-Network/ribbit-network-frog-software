import datetime
import subprocess
import os

include("$(MPY_DIR)/extmod/uasyncio")
freeze("$(PORT_DIR)/modules")
require("neopixel")
require("ntptime")
freeze("modules")
module("microdot.py", "vendor/microdot/src")
module("microdot_asyncio.py", "vendor/microdot/src")
module("microdot_websocket.py", "vendor/microdot/src")

version = subprocess.check_output(
    [
        "git",
        "describe",
        "--tags",  # Necessary because `actions/checkout@v3` doesn't keep the annotated tags for some reason https://github.com/actions/checkout/issues/290
    ],
    encoding="utf-8",
)
commit_id = subprocess.check_output(
    ["git", "rev-parse", "HEAD"],
    encoding="utf-8",
)

if "SOURCE_DATE_EPOCH" in os.environ:
    now = datetime.datetime.utcfromtimestamp(float(os.environ["SOURCE_DATE_EPOCH"]))
else:
    now = datetime.datetime.utcnow()

with open("__version__.py", "w", encoding="utf-8") as f:
    f.write("version = %r\n" % version.strip())
    f.write("commit_id = %r\n" % commit_id.strip())
    f.write("build_date = %r\n" % now.isoformat())
    f.write("build_year = %d\n" % now.year)

os.utime("__version__.py", (now.timestamp(), now.timestamp()))

module("__version__.py")
