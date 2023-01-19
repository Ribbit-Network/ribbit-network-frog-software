class _Driver:
    async def connect(self, disconnect_event):
        """Connect to the network"""
        raise NotImplementedError()

    def status(self):
        """
        Get the status of the network

        Reuses the status defined by `network`:

         * `network.STAT_IDLE`: no connection and no activity,
         * `network.STAT_CONNECTING`: connecting in progress,
         * `network.STAT_WRONG_PASSWORD`: failed due to incorrect password,
         * `network.STAT_NO_AP_FOUND`: failed because no access point replied,
         * `network.STAT_CONNECT_FAIL`: failed due to other problems,
         * `network.STAT_GOT_IP`: connection successful.
        """
        raise NotImplementedError()

    def ifconfig(self):
        """
        Return the IP configuration of the network.

        Returns a 4-tuple (IP address, subnet mask, gateway IP, DNS server IP).
        """
        raise NotImplementedError()
