import socket
import threading
import time

# Define the UDP port to listen on
UDP_IP = "0.0.0.0"  # Listen on all available interfaces
UDP_PORT = 5625
BUFFER_SIZE = 4096  # Adjust as needed
TIMEOUT = 2  # seconds

available_devices = {}
lock = threading.Lock()

def cleanup_inactive_devices():
    while True:
        now = time.time()
        with lock:
            inactive_devices = [mac for mac, (ip, ts) in available_devices.items() if now - ts > TIMEOUT]
            for mac in inactive_devices:
                print(f"Removing inactive device: {mac}")
                del available_devices[mac]
        time.sleep(1) 

def main():
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Bind the socket to the IP and port
    sock.bind((UDP_IP, UDP_PORT))
    print(f"Listening for UDP packets on port {UDP_PORT}...")

    # Start background cleanup thread
    threading.Thread(target=cleanup_inactive_devices, daemon=True).start()

    try:
        while True:
            data, addr = sock.recvfrom(BUFFER_SIZE)  # Receive packet
            ip, port = addr
            content = data.decode(errors='replace')
            if len(content) <= 15:
                print("Beacon packet received")
                mac = content[:12]
                with lock:
                    available_devices[mac] = (ip,time.time())
            print(f"Received packet from {ip}:{port}")
            print(f"available device data: {available_devices}")
            # You can also store this in a file or database if needed
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()