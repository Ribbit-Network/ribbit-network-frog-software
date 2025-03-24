"""
Test the TLS module usage in Golioth client.

This test verifies that the Golioth client correctly uses 
the TLS module for DTLS functionality after the upstream MicroPython
PR #15764 moved DTLS from the ssl module to the tls module.
"""

import unittest
from ribbit.utils.mock import MagicMock, patch

# Import modules we need to test
import tls
import ribbit.golioth as golioth

class TestGoliothDTLS(unittest.TestCase):
    
    def test_golioth_uses_tls_module(self):
        """Test that Golioth client uses the TLS module for DTLS."""
        # Setup mock objects
        original_ssl_context = tls.SSLContext
        mock_context = MagicMock()
        tls.SSLContext = MagicMock(return_value=mock_context)

        try:
            # Create config mock
            mock_config = MagicMock()
            mock_watch = MagicMock()
            mock_config.watch.return_value = mock_watch
            mock_watch.__enter__ = MagicMock(return_value=mock_watch)
            mock_watch.get = MagicMock(return_value=(True, "example.org", 5684, "user", "password", True))
            
            # Create OTA manager mock
            mock_ota_manager = MagicMock()
            
            # Mock asyncio.create_task
            import asyncio
            original_create_task = asyncio.create_task
            asyncio.create_task = MagicMock()
            
            # Create a Golioth client
            client = golioth.Golioth(config=mock_config, ota_manager=mock_ota_manager)
            
            # Verify that the TLS SSLContext was created with DTLS client mode
            tls.SSLContext.assert_called_with(tls.PROTOCOL_DTLS_CLIENT)
            
            # Verify PSK was set
            mock_context.set_ciphers.assert_called()
            mock_context.set_psk.assert_called()
            
        finally:
            # Restore original functions
            tls.SSLContext = original_ssl_context
            asyncio.create_task = original_create_task


def run_tests():
    unittest.main()

if __name__ == '__main__':
    run_tests()