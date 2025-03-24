"""
Test the TLS module usage in Golioth client.

This test verifies that the Golioth client correctly uses 
the TLS module for DTLS functionality after the upstream MicroPython
PR #15764 moved DTLS from the ssl module to the tls module.
"""

import unittest
from unittest.mock import patch, MagicMock

# Import modules we need to test
import tls
import ribbit.golioth as golioth

class TestGoliothDTLS(unittest.TestCase):
    
    @patch('tls.SSLContext')
    def test_golioth_uses_tls_module(self, mock_ssl_context):
        """Test that Golioth client uses the TLS module for DTLS."""
        # Setup mock objects
        mock_context = MagicMock()
        mock_ssl_context.return_value = mock_context

        # Create config mock
        mock_config = MagicMock()
        mock_watch = MagicMock()
        mock_config.watch.return_value = mock_watch
        mock_watch.__enter__.return_value = mock_watch
        mock_watch.get.return_value = (True, "example.org", 5684, "user", "password", True)
        
        # Create OTA manager mock
        mock_ota_manager = MagicMock()
        
        # Create a Golioth client
        client = golioth.Golioth(config=mock_config, ota_manager=mock_ota_manager)
        
        # Verify that the TLS SSLContext was created with DTLS client mode
        mock_ssl_context.assert_called_with(tls.PROTOCOL_DTLS_CLIENT)
        
        # Verify PSK was set
        mock_context.set_ciphers.assert_called_with(["TLS-PSK-WITH-AES-128-CBC-SHA256"])
        mock_context.set_psk.assert_called_with("user", "password")


def run_tests():
    unittest.main()

if __name__ == '__main__':
    run_tests()