import socket
import struct
import threading
import time
import random
from typing import Tuple, Optional

#github_link = https://github.com/IdanDuha/Communication-System-Hackaton.git


class Server:
    """Server implementation for the speed test application"""
    
    MAGIC_COOKIE = 0xabcddcba
    MSG_TYPE_OFFER = 0x2
    MSG_TYPE_REQUEST = 0x3
    MSG_TYPE_PAYLOAD = 0x4

    def __init__(self):
        # Initialize UDP and TCP sockets, bind them to ports
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        self.udp_socket.bind(('', 0))
        self.tcp_socket.bind(('', 0))
        
        self.udp_port = self.udp_socket.getsockname()[1]
        self.tcp_port = self.tcp_socket.getsockname()[1]
        
       
        self.ip_address = self._get_local_ip()
        
        # Start listening on TCP socket
        self.tcp_socket.listen(5)
        
        print(f"Server started, listening on IP address {self.ip_address}")
    def _get_local_ip(self) -> str:
        try:
            # Get all network interfaces
            hostname = socket.gethostname()
            ip_addresses = socket.gethostbyname_ex(hostname)[2]
        
            # Filter out localhost and try to get the correct network interface
            for ip in ip_addresses:
                if not ip.startswith('127.'):  # Skip localhost
                    return ip
                
            # If no suitable IP found, get all network interfaces
            interfaces = []
            for if_name in socket.if_nameindex():
                try:
                    if_ip = socket.gethostbyname(if_name[1])
                    if not if_ip.startswith('127.'):
                        interfaces.append(if_ip)
                except:
                    continue
                
            if interfaces:
                return interfaces[0]
                
            raise RuntimeError("No suitable network interface found")
        except Exception as e:
            print(f"Error getting local IP: {e}")
            # Instead of returning localhost, raise an error
            raise RuntimeError("Could not determine local IP address")

    def start(self):
        """Start the server's main operations"""
        # Start the offer broadcast thread
        offer_thread = threading.Thread(target=self._broadcast_offers)
        offer_thread.daemon = True
        offer_thread.start()
        
        # Start accepting TCP connections
        tcp_accept_thread = threading.Thread(target=self._accept_tcp_connections)
        tcp_accept_thread.daemon = True
        tcp_accept_thread.start()
        
        # Start handling UDP requests
        udp_handler_thread = threading.Thread(target=self._handle_udp_requests)
        udp_handler_thread.daemon = True
        udp_handler_thread.start()
        
        try:
            # keep the server alive
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.cleanup()

    def _broadcast_offers(self):
        """Continuously broadcast offer messages"""
        broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
        # Bind to the same interface we're listening on
        broadcast_socket.bind((self.ip_address, 0))
    
        offer_message = struct.pack('!IbHH',
            self.MAGIC_COOKIE,
            self.MSG_TYPE_OFFER,
            self.udp_port,
            self.tcp_port
        )
    
        while True:
            try:
                broadcast_socket.sendto(offer_message, ('255.255.255.255', 13117))
                print(f"Sent broadcast from {self.ip_address}")
                time.sleep(1)
            except Exception as e:
                print(f"Error broadcasting offer: {e}")
                
    def _handle_tcp_client(self, client_socket: socket.socket, address: Tuple[str, int]):
        """Handle individual TCP client connections"""
        try:
            data = client_socket.recv(1024).decode()
            if not data.endswith('\n'):
                raise ValueError("Invalid request format")
            
            file_size = int(data.strip())
            
            # Generate and send random data
            bytes_sent = 0
            chunk_size = 8*1024  # 8KB chunks
            
            while bytes_sent < file_size:
                remaining = file_size - bytes_sent
                chunk = random.randbytes(min(chunk_size, remaining))
                client_socket.sendall(chunk)
                bytes_sent += len(chunk)
                
        except Exception as e:
            print(f"Error handling TCP client {address}: {e}")
        finally:
            client_socket.close()

    def _accept_tcp_connections(self):
      
        while True:
            try:
                client_socket, address = self.tcp_socket.accept()
                client_thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                print(f"Error accepting TCP connection: {e}")

    def _handle_udp_requests(self):
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                if len(data) < 13:  #min size
                    continue
                
                magic_cookie, msg_type, file_size = struct.unpack('!IbQ', data[:13])
                
                if magic_cookie != self.MAGIC_COOKIE or msg_type != self.MSG_TYPE_REQUEST:
                    continue
                
                transfer_thread = threading.Thread(
                    target=self._handle_udp_transfer,
                    args=(addr, file_size)
                )
                transfer_thread.daemon = True
                transfer_thread.start()
                
            except Exception as e:
                print(f"Error handling UDP request: {e}")

    def _handle_udp_transfer(self, client_addr: Tuple[str, int], file_size: int):
        """Handle individual UDP file transfers"""
        try:
            bytes_sent = 0
            segment_size = 1024  # 1KB segments
            total_segments = (file_size + segment_size - 1) // segment_size
            current_segment = 0
            
            while bytes_sent < file_size:
                remaining = file_size - bytes_sent
                payload_size = min(segment_size, remaining)
                payload = random.randbytes(payload_size)
                
                header = struct.pack('!IbQQ',
                    self.MAGIC_COOKIE,
                    self.MSG_TYPE_PAYLOAD,
                    total_segments,
                    current_segment
                )
                
                packet = header + payload
                self.udp_socket.sendto(packet, client_addr)
                
                bytes_sent += payload_size
                current_segment += 1
        except Exception as e:
            print(f"Error handling UDP transfer to {client_addr}: {e}")

    def cleanup(self):
        """Clean up resources"""
        self.udp_socket.close()
        self.tcp_socket.close()

if __name__ == "__main__":
    server = Server()
    server.start()
