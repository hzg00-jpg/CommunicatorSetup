import math
import random
import socket
import ssl
import threading
import time
# pip install math random socket ssl threading time

"""
Corresponds with the stealth based server.
"""

HEADER = 16 
SIZES_LIST = [256, 384, 512, 640, 768, 896, 1024]

PORT = 5000 # Use 443 when outside testing, HTTPS
SERVER = "ENTER YOUR PRIVATE IP"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!disconnect"

AVG_POISSON_DELAY = 2 # n amounts of messages per second
DUMMY_TRAFFIC = "OFF" # Either OFF or ON


context = ssl.create_default_context()
context.load_verify_locations("certificate.crt") # trust the certificate

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client = context.wrap_socket(client, server_hostname="auth.internal-auth.net")
client.connect(ADDR)

verified = False

def determine_padding(msg_length):
    """
    Slightly tweaked block padding.
    """
    suitable_sizes = [sizes for sizes in SIZES_LIST if sizes > msg_length]
    selected_random_size = random.choice(suitable_sizes)

    num = random.randint(msg_length, selected_random_size) - msg_length - 16 - 5
    return str(num).zfill(4) # Always fills it to 4 digits. Won't exceed 4, SIZES_LIST caps at 4 digits.


def send(msg):
    """
    Sends bytes to the server. 

    Socket exchanges sends specific byte data, so you must know the number of bytes the message you send contains. 
    A workaround is sending a header and a message. The header contains the length of the message, which tells the 
    client the number of bytes the next send (the message) contains.

    Differs from the server send function in that each client has only one 'conn' identity, which is itself.

    msg: Message to be sent
    """
    message = msg.encode(FORMAT) # Converts from strings to bytes to be sent later

    filler = determine_padding(len(msg)).encode(FORMAT)

    header = str(len(message)).encode(FORMAT) 
    header += b' ' * (HEADER - len(header)) # Header is always 16 bytes
    
    frame = "REALL".encode(FORMAT) + filler + header + message
    # frame = filler + header + message
    frame += b' ' * int(filler)

    client.sendall(frame) # Sends everything, header and message to server, combined in a frame


def send_dummy():
    """
    Sends a 5 byte differentiating message, then a 4 byte length message that corresponds to the length of the padding.
    [DUMMY][xxxx][padding]
    """
    message = "DUMMY".encode(FORMAT)
    random_choice = random.choice(SIZES_LIST)
    random_size = random.randint(9, random_choice)
    rand_size_4_digits = str(random_size).zfill(4)

    message = message + rand_size_4_digits.encode(FORMAT)
    message += b' ' * (random_size - 9) # Subtract 9, so the total size is random_size

    client.sendall(message)


def recv_all(conn, n):
    """
    Receive exactly n bytes from the socket.
    Returns bytes or None if connection is closed.
    """
    data = b""

    while len(data) < n:
        packet = conn.recv(n - len(data))

        if not packet:  # connection closed
            return None

        data += packet
    return data

def receive():
    """
    Receives data from the server. 
    """
    while True:
        try:
            global verified
            
            gate = recv_all(client, 5)
            if not gate:
                pass # Passes onto if not read_first_four, which will return "Disconnected."
            elif gate.decode(FORMAT) == "DUMMY":
                read_first_four = recv_all(client, 4)
                padding_length = int(read_first_four)

                recv_all(client, padding_length - 9)
                continue

            read_first_four = recv_all(client, 4)
            if not read_first_four:
                print("Disconnected.")
                break
            padding_length = int(read_first_four)

            read_header = recv_all(client, 16)
            if not read_header:
                print("Disconnected.")
                break
            header = read_header.decode(FORMAT)
            msg_length = int(header.strip())

            message = recv_all(client, msg_length + padding_length) # frame = header + msg
            if not message:
                print("Disconnected.")
                break
            msg = message[0 : msg_length].decode(FORMAT)

            if msg == "VERIFICATION COMPLETE":
                verified = True
                continue

            print(msg) # Prints the received message (from broadcast). Also handles the initial connection message.

        except Exception as e: # Most connection closes are caught by if not header
            break

    client.close()

threading.Thread(target=receive, daemon=True).start() 
# Creates a receive thread object to allow the client to receive messages and accept user input at the same time.


def get_poisson_delay():
    u = random.uniform(0.00001, 1.0)
    return -math.log(u) / AVG_POISSON_DELAY


def dummy_traffic():
    """
    Creates dummy traffic to the server.
    """
    while True:

        if DUMMY_TRAFFIC != "ON":
            break

        if not verified:
            time.sleep(0.1)
            continue

        time.sleep(random.expovariate(2)) 
        try:
            send_dummy()
        except Exception as e:
            print(f"Dummy send failed: {e}") # Mostly prints when the server is disconnected but client is still connected
            client.close() 
            break
    
threading.Thread(target=dummy_traffic, daemon=True).start() 
# Dummy traffic threading. The thread starts regardless of whether or not verification is passed. To prevent spam, server-side
# has a max number of verifications that can occur at one time. 


# Loop that asks the user for input
running = True

while running:
    try:
        user_input = input()
        send(user_input)
    except OSError:
        running = False