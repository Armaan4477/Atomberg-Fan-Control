import json
import socket 

TARGET_IP_1 = "192.168.29.14" #sofa fan
TARGET_IP_2 = "192.168.29.15" #table fan
TARGET_PORT = 5600

# Step 1: Select which fan to control
print("\n=== Atomberg Fan Control ===")
print("1. Sofa Fan (192.168.29.14)")
print("2. Table Fan (192.168.29.15)")
fan_choice = input("\nWhich fan do you want to control? (1/2): ").strip()

if fan_choice == "1":
    target_ip = TARGET_IP_1
    fan_name = "Sofa Fan"
elif fan_choice == "2":
    target_ip = TARGET_IP_2
    fan_name = "Table Fan"
else:
    print("Invalid choice!")
    exit()

print(f"\nControlling: {fan_name}")

# Step 2: Select what to do
print("\n=== Select Action ===")
print("1. Turn ON")
print("2. Turn OFF")
print("3. Set Speed")
print("4. Change Speed (Delta)")
print("5. Toggle LED")
print("6. Set Timer")
print("7. Toggle Sleep Mode")
action = input("\nWhat would you like to do? (1-7): ").strip()

# Initialize empty command - only send what changes
command = {}

# Process the action
if action == "1":  # Turn ON
    command["power"] = True
    print("Turning fan ON")
elif action == "2":  # Turn OFF
    command["power"] = False
    print("Turning fan OFF")
elif action == "3":  # Set Speed
    speed = input("Enter speed (0-6): ").strip()
    command["speed"] = int(speed)
    print(f"Setting speed to {speed}")
elif action == "4":  # Speed Delta
    delta = input("Enter speed delta (-1 to 5, except 0): ").strip()
    command["speedDelta"] = int(delta)
    print(f"Changing speed by {delta}")
elif action == "5":  # Toggle LED
    led_choice = input("LED ON or OFF? (on/off): ").strip().lower()
    command["led"] = True if led_choice == "on" else False
    print(f"Setting LED to {led_choice.upper()}")
elif action == "6":  # Set Timer
    timer = input("Enter timer value (0-4): ").strip()
    command["timer"] = int(timer)
    print(f"Setting timer to {timer}")
elif action == "7":  # Toggle Sleep
    sleep_choice = input("Sleep mode ON or OFF? (on/off): ").strip().lower()
    command["sleep"] = True if sleep_choice == "on" else False
    print(f"Setting sleep mode to {sleep_choice.upper()}")
else:
    print("Invalid action!")
    exit()

# Convert to JSON string and encode to bytes
message = json.dumps(command).encode('utf-8')

# Create UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Send the message
sock.sendto(message, (target_ip, TARGET_PORT))
print(f"\n✓ Command sent to {fan_name} ({target_ip}:{TARGET_PORT})")
print(f"Command: {json.dumps(command, indent=2)}")

# Close the socket
sock.close()