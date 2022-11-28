This is a variant of the "standard" Micropython unix port, with one
key difference: it enables the `MICROPY_PY_USELECT` option to use
the same polling mechanism as the ESP32 port instead of using the
system file-descriptor based polling that doesn't support ssl sockets
properly yet.