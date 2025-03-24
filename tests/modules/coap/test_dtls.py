"""
Test the TLS module usage in CoAP and Golioth clients.

This test verifies that the CoAP and Golioth modules correctly use 
the TLS module for DTLS functionality after the upstream MicroPython
PR #15764 moved DTLS from the ssl module to the tls module.
"""

import unittest
import socket
import io
from unittest.mock import patch, MagicMock

# Import modules we need to test
import tls
from ribbit.coap import Coap
import ribbit.golioth as golioth

class DummySocket(io.IOBase):
    def __init__(self):
        self.write_buffer = bytearray()
        self.read_buffer = bytearray()
        self.closed = False

    def send(self, data):
        self.write_buffer.extend(data)
        return len(data)
    
    def recv(self, size):
        return b''
    
    def close(self):
        self.closed = True

    def setblocking(self, value):
        pass
        
    def connect(self, addr):
        pass
        
    def bind(self, addr):
        pass


class TestCoAPDTLS(unittest.TestCase):
    
    def setUp(self):
        self.original_getaddrinfo = socket.getaddrinfo
        socket.getaddrinfo = MagicMock(return_value=[(None, None, None, None, ('127.0.0.1', 5684))])
        
    def tearDown(self):
        socket.getaddrinfo = self.original_getaddrinfo
        
    @patch('tls.SSLContext')
    @patch('socket.socket')
    def test_coap_uses_tls_module(self, mock_socket, mock_ssl_context):
        """Test that CoAP client uses the TLS module for DTLS."""
        # Setup mock objects
        mock_socket_instance = MagicMock()
        mock_socket.return_value = mock_socket_instance
        
        mock_context = MagicMock()
        mock_ssl_context.return_value = mock_context
        mock_wrapped_socket = MagicMock()
        mock_context.wrap_socket.return_value = mock_wrapped_socket
        
        # Create a CoAP client with DTLS enabled
        coap = Coap(
            host="example.org",
            port=5684,
            ssl=True  # Enable DTLS
        )
        
        # This should trigger the creation of the SSLContext with DTLS client mode
        try:
            import asyncio
            asyncio.run_until_complete = MagicMock()
            asyncio.create_task = MagicMock()
            asyncio.Event = MagicMock()
            
            # Call connect to initialize the socket with TLS
            coap.connect()
        except Exception:
            # We expect an exception due to incomplete mocking of asyncio
            pass
            
        # Verify that the TLS SSLContext was created with DTLS client mode
        mock_ssl_context.assert_called_with(tls.PROTOCOL_DTLS_CLIENT)
        
        # Verify that the socket was wrapped with wrap_socket
        mock_context.wrap_socket.assert_called()


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


if __name__ == '__main__':
    unittest.main()