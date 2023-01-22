import hashlib
import logging
from binascii import hexlify


class OTAUpdate:
    def __init__(self, reader, sha256_hash, size):
        self.reader = reader
        self.sha256_hash = sha256_hash
        self.size = size


class OTAManager:
    def __init__(self, in_simulator=False):
        self._logger = logging.getLogger(__name__)
        self._in_simulator = in_simulator

    def successful_boot(self):
        if self._in_simulator:
            self._logger.info("Running in simulator: skipping successful boot")
            return

        import esp32
        esp32.Partition.mark_app_valid_cancel_rollback()

    async def do_ota_update(self, u):
        if self._in_simulator:
            self._logger.info("Running in simulator: skipping update")
            return

        import esp32

        self._logger.info("Starting OTA update")
        partition = esp32.Partition(esp32.Partition.RUNNING).get_next_update()
        h = hashlib.sha256()

        block_count = partition.ioctl(4, None)
        block_size = partition.ioctl(5, None)

        self._logger.info("Block size is %d, update size is %d", block_size, u.size)

        if block_size * block_count < u.size:
            raise Exception(
                "Update is too large: has %d bytes, need %d bytes",
                block_size * block_count,
                u.size,
            )

        multiplier = 4
        buf = memoryview(bytearray(block_size * multiplier))
        block_id = 0
        total_read = 0
        while total_read < u.size:
            if block_id % 10 == 0:
                self._logger.info(
                    "Processing block %d (%.2f %%)", block_id, 100 * total_read / u.size
                )

            dest_buf = buf[: u.size - total_read]

            n = 0
            while n < len(dest_buf):
                try:
                    sz = await u.reader.readinto(dest_buf[n:])
                except:
                    self._logger.warning("Exception processing coap block id %d. Trying again.", block_id)
                    # Attempt to read this block again
                    continue
                if sz == 0:
                    break
                n += sz

            if n != len(dest_buf):
                raise Exception("unexpected EOF")

            total_read += n

            h.update(buf[:n])

            # For the last block, zero out the rest of the buffer
            while n < len(buf):
                buf[n] = 0
                n += 1

            partition.ioctl(6, block_id)
            partition.writeblocks(block_id, buf)
            block_id += multiplier

        partition.ioctl(
            3, None
        )  # Sync the device, probably a no-op but it doesn't hurt

        self._logger.info("Finished flashing")

        hash = hexlify(h.digest())
        if hash.decode("ascii") != u.sha256_hash:
            raise Exception("Wrong hash: got %s, expected %s", hash, u.sha256_hash)

        partition.set_boot()
