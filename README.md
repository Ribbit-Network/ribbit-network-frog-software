# Ribbit Frog on Micropython

This is an experiment in building a Ribbit Frog sensor on Micropython.

## Building

Fetch the submodules:

```shell
$ git submodule update --jobs 32 --init --recursive
```

Run tests:

```shell
$ make test
```

Build the firmware:

```shell
$ make build
```

Flash the firmware to a device connected to `/dev/ttyACM*`:

```shell
$ make flash
```