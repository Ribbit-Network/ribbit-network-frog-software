import os

BASE_PATH = "modules/ribbit/sensor-ui/"

with open("modules/ribbit/_static.py", "w") as o:
    o.write("assets = {\n")
    first = True

    for dirpath, dirs, files in os.walk(BASE_PATH):
        assert dirpath.startswith(BASE_PATH)
        relative_dirpath = "/" + dirpath[len(BASE_PATH):]
        for filename in files:
            relative_filepath = os.path.join(relative_dirpath, filename)
            filepath = os.path.join(dirpath, filename)

            if not first:
                o.write("\n")
            else:
                first = False

            with open(filepath, "rb") as f:
                o.write("  %r: %r,\n" % (relative_filepath, f.read()))

    o.write("}\n")
