#define MICROPY_HW_BOARD_NAME               "Ribbit Frog Sensor v4"
#define MICROPY_HW_MCU_NAME                 "ESP32-S3"

#define MICROPY_PY_BLUETOOTH                (0)
#define MICROPY_PY_MACHINE_DAC              (0)

// Enable UART REPL for modules that have an external USB-UART and don't use native USB.
#define MICROPY_HW_ENABLE_UART_REPL         (1)

#define MICROPY_HW_I2C0_SCL                 (4)
#define MICROPY_HW_I2C0_SDA                 (3)

#define MICROPY_ENABLE_COMPILER             (1)

#define MICROPY_PY_ESPNOW                   (0)
#define MICROPY_PY_MACHINE_I2S              (0)
#define MICROPY_HW_ENABLE_SDCARD            (0)
