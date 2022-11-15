set(IDF_TARGET esp32s3)

set(SDKCONFIG_DEFAULTS
    boards/sdkconfig.base
    boards/sdkconfig.usb
    boards/sdkconfig.240mhz
    boards/sdkconfig.spiram_sx
    boards/ribbit/sdkconfig.board
)
