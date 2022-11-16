import datetime
import subprocess

include("$(MPY_DIR)/extmod/uasyncio")
freeze("$(PORT_DIR)/modules")
require("neopixel")
require("ntptime")
freeze("modules")
module("microdot.py", "vendor/microdot/src")
module("microdot_asyncio.py", "vendor/microdot/src")

version = subprocess.check_output(
    ["git", "describe"],
    encoding="utf-8",
)
commit_id = subprocess.check_output(
    ["git", "rev-parse", "HEAD"],
    encoding="utf-8",
)
now = datetime.datetime.utcnow()

with open("__version__.py", "w", encoding="utf-8") as f:
    f.write("version = %r\n" % version.strip())
    f.write("commit_id = %r\n" % commit_id.strip())
    f.write("build_date = %r\n" % now.isoformat())
    f.write("build_year = %d\n" % now.year)

module("__version__.py")
