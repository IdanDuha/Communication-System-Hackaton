#!/usr/bin/env python3
import socket
import struct
import threading
import time
from typing import List, Tuple, Dict, Set
from dataclasses import dataclass
import sys


github_link = https://github.com/IdanDuha/Communication-System-Hackaton.git

@dataclass
class TransferStats:
    """Statistics for a single transfer"""
    transfer_id: int
    protocol: str
    start_time: float
    end_time: float = 0
    bytes_received: int = 0
    packets_received: int = 0  # For UDP only
    total_packets: int = 0     # For UDP only

class SpeedTestClient:
    """Client implementation for the speed test application"""
    
    MAGIC_COOKIE = 0xabcddcba
    MSG_TYPE_OFFER = 0x2
    MSG_TYPE_REQUEST = 0x3
    MSG_TYPE_PAYLOAD = 0x4
    
    def __init__(self):
        self.udp_socket = None
        try:
            # Create UDP socket for receiving offers
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.udp_socket.bind(('', 13117))
        except Exception as e:
            print(f"Error initializing client: {e}")
            if self.udp_socket:
                self.udp_socket.close()
            raise
            
        # State tracking
        self.current_server: Tuple[str, int, int] = None  # (ip, udp_port, tcp_port)
        self.active_transfers: Dict[int, TransferStats] = {}
        self.transfer_counter = 0
        self.running = True

    def start(self):
        """"basicly the main"""
        
        print("Client started, listening for offer requests...")
        
        while self.running:
            try:
                # Get parameters from user
                file_size = self._get_user_input("Enter file size (bytes): ", int)
                tcp_count = self._get_user_input("Enter number of TCP connections: ", int)
                udp_count = self._get_user_input("Enter number of UDP connections: ", int)
                
                # Wait for and connect to a server
                self._wait_for_server()
                
                # Start the transfers
                self._run_speed_test(file_size, tcp_count, udp_count)
                
                print("All transfers complete, listening to offer requests")
                
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"Error during speed test: {e}")
                time.sleep(1)
            
        # Cleanup only when completely done
        if self.udp_socket:
            self.udp_socket.close()

    def _get_user_input(self, prompt: str, type_func):
        """Get and validate user input"""
        while True:
            try:
                value = type_func(input(prompt))
                if value <= 0:
                    raise ValueError("Value must be positive")
                return value
            except ValueError as e:
                print(f"Invalid input: {e}")
            finally:
                pass  # No resources to clean up

    def _wait_for_server(self):
        """Wait for a server offer message"""
        self.current_server = None
        print("Waiting for server offer...")
        
        while self.running and not self.current_server:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                if len(data) < 9:  # Minimum offer message size
                    continue
                
                magic_cookie, msg_type, udp_port, tcp_port = struct.unpack('!IbHH', data[:9])
                
                if magic_cookie == self.MAGIC_COOKIE and msg_type == self.MSG_TYPE_OFFER:
                    server_ip = addr[0]
                    print(f"Received offer from {server_ip}")
                    self.current_server = (server_ip, udp_port, tcp_port)
                    
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving offer: {e}")
            finally:
                pass  # Socket cleanup handled in start() method

    def _run_speed_test(self, file_size: int, tcp_count: int, udp_count: int):
        """Run the speed test with specified parameters"""
        threads: List[threading.Thread] = []
        
        try:
            counter =1
            # Start TCP transfers
            for i in range(tcp_count):
                thread = threading.Thread(
                    target=self._handle_tcp_transfer,
                    args=(i + counter, file_size)
                )
                thread.start()
                threads.append(thread)
            
            # Start UDP transfers
            for i in range(udp_count):
                thread = threading.Thread(
                    target=self._handle_udp_transfer,
                    args=(counter + i+1 , file_size)
                )
                thread.start()
                threads.append(thread)
            
            # Wait for all transfers to complete
            for thread in threads:
                thread.join()
        except Exception as e:
            print(f"Error in speed test: {e}")
        finally:
            # Ensure all threads are cleaned up
            for thread in threads:
                if thread.is_alive():
                    thread.join(timeout=1.0)

    def _handle_tcp_transfer(self, transfer_id: int, file_size: int):
        """Handle a single TCP transfer"""
        sock = None
        try:
            # Create socket and connect
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.current_server[0], self.current_server[2]))
            
            # Initialize statistics
            stats = TransferStats(transfer_id, "TCP", time.time())
            self.active_transfers[transfer_id] = stats
            
            # Send file size request
            sock.sendall(f"{file_size}\n".encode())
            
            # Receive data
            bytes_received = 0
            while bytes_received < file_size:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                bytes_received += len(chunk)
                stats.bytes_received = bytes_received
            
            # Record completion
            stats.end_time = time.time()
            self._print_transfer_stats(stats)
            
        except Exception as e:
            print(f"Error in TCP transfer {transfer_id}: {e}")
        finally:
            if sock:
                sock.close()

    def _handle_udp_transfer(self, transfer_id: int, file_size: int):
        """Handle a single UDP transfer"""
        udp_socket = None
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(1.0)  # 1 second timeout
            stats = TransferStats(transfer_id, "UDP", time.time())
            self.active_transfers[transfer_id] = stats            
            request = struct.pack('!IbQ',
                self.MAGIC_COOKIE,
                self.MSG_TYPE_REQUEST,
                file_size
            )
            udp_socket.sendto(request, (self.current_server[0], self.current_server[1]))
            
            # Receive data
            received_segments: Set[int] = set()
            last_packet_time = time.time()
            bytes_received = 0
            
            while True:
                try:
                    data, _ = udp_socket.recvfrom(2048)
                    last_packet_time = time.time()
                    
                    if len(data) < 21:  # Minimum payload message size
                        continue
                    
                    magic_cookie, msg_type, total_segments, segment_num = struct.unpack('!IbQQ', data[:21])
                    
                    if magic_cookie != self.MAGIC_COOKIE or msg_type != self.MSG_TYPE_PAYLOAD:
                        continue
                    
                    if segment_num not in received_segments:
                        received_segments.add(segment_num)
                        bytes_received += len(data[21:])
                        stats.bytes_received = bytes_received
                        stats.packets_received += 1
                        stats.total_packets = total_segments
                    
                except socket.timeout:
                    if time.time() - last_packet_time > 1.0:
                        break
                except Exception as e:
                    print(f"Error receiving UDP data in transfer {transfer_id}: {e}")
                    break
                finally:
                    pass  
            
            # Record completion
            stats.end_time = time.time()
            self._print_transfer_stats(stats)
            
        except Exception as e:
            print(f"Error in UDP transfer {transfer_id}: {e}")
        finally:
            if udp_socket:
                udp_socket.close()

    def _print_transfer_stats(self, stats: TransferStats):
        """Print statistics for a completed transfer"""
        try:
            duration = stats.end_time - stats.start_time
            speed = (stats.bytes_received * 8) / duration  # Convert to bits/second
            
            if stats.protocol == "TCP":
                print(f"TCP transfer #{stats.transfer_id} finished, "
                      f"total time: {duration:.2f} seconds, "
                      f"total speed: {speed:.1f} bits/second")
            else:
                success_rate = (stats.packets_received / stats.total_packets * 100) if stats.total_packets > 0 else 0
                print(f"UDP transfer #{stats.transfer_id} finished, "
                      f"total time: {duration:.2f} seconds, "
                      f"total speed: {speed:.1f} bits/second, "
                      f"percentage of packets received successfully: {success_rate:.1f}%")
        except Exception as e:
            print(f"Error printing stats: {e}")
        finally:
            pass  # No resources to clean up

    def cleanup(self):
        """Clean up resources"""
        try:
            self.running = False
            if self.udp_socket:
                self.udp_socket.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            pass  # No additional resources to clean up

if __name__ == "__main__":
    client = None
    try:
        client = SpeedTestClient()
        client.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        if client:
            client.cleanup()
