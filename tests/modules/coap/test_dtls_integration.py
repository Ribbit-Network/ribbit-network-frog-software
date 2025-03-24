"""
Integration test for DTLS functionality in CoAP client.

This test creates a basic server and client to verify proper DTLS operation.
To run this test, you need a proper DTLS server or a mock server.

Note: This test is intended to be run manually when verifying DTLS changes.
"""

import asyncio
import tls
import socket
from ribbit.coap import Coap, CoapPacket, TYPE_CON, METHOD_GET

# This is a basic integration test that can be run manually
# to test the DTLS functionality with actual server

async def test_coap_dtls_connection():
    """Test connecting to a CoAP server with DTLS enabled."""
    
    # Create a TLS context for DTLS
    ctx = tls.SSLContext(tls.PROTOCOL_DTLS_CLIENT)
    
    # You may need to configure the context with PSK or certificates
    # ctx.set_ciphers(["TLS-PSK-WITH-AES-128-CBC-SHA256"])
    # ctx.set_psk("user_id", "password")
    
    # Replace with your CoAP+DTLS server address and port
    coap_server = "coap.example.com"
    coap_port = 5684
    
    try:
        # Create CoAP client with DTLS enabled
        coap = Coap(
            host=coap_server,
            port=coap_port,
            ssl=ctx
        )
        
        # Connect to the server
        print(f"Connecting to {coap_server}:{coap_port} with DTLS...")
        await coap.connect()
        
        print("Connected successfully. Sending ping...")
        await coap.ping()
        print("Ping successful!")
        
        # Try to fetch a resource
        print("Fetching resource...")
        response = await coap.get(".well-known/core")
        print(f"Response received: {response}")
        
        # Clean up
        await coap.disconnect()
        print("Test completed successfully")
        
    except Exception as e:
        print(f"Error in DTLS test: {e}")
        raise

# Local test server setup - you can implement a simple DTLS server here
# if needed for testing without depending on an external service

class DtlsTestServer:
    """Minimal DTLS test server for testing the client."""
    def __init__(self, host="0.0.0.0", port=5684):
        self.host = host
        self.port = port
        self.socket = None
        self.context = None
        
    async def start(self):
        """Start the DTLS test server."""
        # Create a TLS context for DTLS server
        self.context = tls.SSLContext(tls.PROTOCOL_DTLS_SERVER)
        
        # For testing, we can use a self-signed certificate
        # self.context.load_cert_chain("cert.pem", "key.pem")
        
        # Or PSK for simpler setup
        # self.context.set_ciphers(["TLS-PSK-WITH-AES-128-CBC-SHA256"])
        # self.context.set_psk("user_id", "password")
        
        # Create and bind the socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.host, self.port))
        
        print(f"DTLS test server starting on {self.host}:{self.port}")
        
        # Wrap the socket with DTLS
        self.socket = self.context.wrap_socket(
            self.socket,
            server_side=True
        )
        
        # Handle incoming connections
        while True:
            try:
                data, addr = self.socket.recvfrom(1024)
                print(f"Received {len(data)} bytes from {addr}")
                
                # Send a response
                response = b"\x60\x45\x00\x01\x00\x00\x00\x00\xFF\x68\x65\x6C\x6C\x6F"  # CoAP response
                self.socket.sendto(response, addr)
            except Exception as e:
                print(f"Error handling connection: {e}")
                
    def stop(self):
        """Stop the DTLS test server."""
        if self.socket:
            self.socket.close()

if __name__ == "__main__":
    # Run the client test
    asyncio.run(test_coap_dtls_connection())
    
    # Uncomment to run the server instead
    # server = DtlsTestServer()
    # asyncio.run(server.start())