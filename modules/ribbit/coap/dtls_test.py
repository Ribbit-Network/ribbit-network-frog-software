"""
Test the TLS module usage in CoAP clients.

This test verifies that the CoAP module correctly uses 
the TLS module for DTLS functionality after the upstream MicroPython
PR #15764 moved DTLS from the ssl module to the tls module.
"""

import unittest
import socket
import io
from ribbit.utils.mock import MagicMock, patch

# Import modules we need to test
import tls
from ribbit.coap import Coap

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
    
    def test_coap_uses_tls_module(self):
        """Test that CoAP client uses the TLS module for DTLS."""
        # Create mock objects
        mock_socket = MagicMock()
        mock_socket_instance = MagicMock()
        mock_socket.return_value = mock_socket_instance
        
        original_socket = socket.socket
        socket.socket = mock_socket
        
        mock_context = MagicMock()
        mock_wrap_socket = MagicMock()
        mock_context.wrap_socket = mock_wrap_socket
        
        original_ssl_context = tls.SSLContext
        tls.SSLContext = MagicMock(return_value=mock_context)
        
        try:
            # Create a CoAP client with DTLS enabled
            coap = Coap(
                host="example.org",
                port=5684,
                ssl=True  # Enable DTLS
            )
            
            # Mock asyncio for connect
            import asyncio
            original_create_task = asyncio.create_task
            asyncio.create_task = MagicMock()
            original_event = asyncio.Event
            asyncio.Event = MagicMock()
            
            try:
                # Call connect to initialize the socket with TLS
                coap.connect()
            except Exception as e:
                # We expect an exception due to incomplete mocking of asyncio
                pass
                
            # Verify that the TLS SSLContext was created with DTLS client mode
            tls.SSLContext.assert_called_with(tls.PROTOCOL_DTLS_CLIENT)
            
            # Verify that wrap_socket was called
            mock_context.wrap_socket.assert_called()
            
        finally:
            # Restore original functions
            socket.socket = original_socket
            tls.SSLContext = original_ssl_context
            asyncio.create_task = original_create_task
            asyncio.Event = original_event


def run_tests():
    unittest.main()

if __name__ == '__main__':
    run_tests()