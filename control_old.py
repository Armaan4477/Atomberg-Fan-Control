import json
import socket 

TARGET_IP = "192.168.29.14"
TARGET_PORT = 5600

# JSON command to send
command = {
    "led":False
}

# Convert to JSON string and encode to bytes
message = json.dumps(command).encode('utf-8')

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send the message
sock.sendto(message, (TARGET_IP, TARGET_PORT))
print(f"Sent JSON command to {TARGET_IP}:{TARGET_PORT}")

# Close the socket
sock.close()