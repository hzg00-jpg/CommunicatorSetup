import random
import secrets
import socket
import ssl
import threading
import time
# pip install random secrets socket ssl threading time

"""
Stealth based server that focuses on blending into regular traffic.
"""

HEADER = 16
SIZES_LIST = [256, 384, 512, 640, 768, 896, 1024]

PORT = 5000 # 5000 is for testing, use a more natural port such as 443 when outside testing.
SERVER = socket.gethostbyname(socket.gethostname())
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!disconnect"
DUMMY_TRAFFIC = "OFF" # Either OFF or ON

MAX_VERIFICATION = 5 # Maximum number of people who can be in the verification system at one time

context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile="certificate.crt", keyfile="key.key")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients = [] # Verified connections
connected = [] # Anyone who connects

verification = [] # Contains tuples of (key, port)

# Semaphore for verification
verifying_limit = threading.Semaphore(MAX_VERIFICATION)

def verification(conn, addr):
    """
    Single verification. If it passes, conn gets connected. Otherwise, conn gets disconnected. Can reconnect and try again.

    conn: The socket object performing the action. Each new connection creates a new socket object which has a unique conn

    addr: A tuple containing the client's IP and port
    """ 
    if not verifying_limit.acquire(blocking=False):
        send(conn, "Server busy. Try again.")
        conn.close()
        return False

    try:
        code = secrets.randbelow(1_000_000)
        print(f"Port {addr[1]}'s code is {code}")
        send(conn, f"You are on port {addr[1]}.")
        send(conn, "Enter verification code:")

        recv_all(conn, 5) # No dummy traffic here in verification, just read and discard

        read_first_four = recv_all(conn, 4)
        if not read_first_four:
            return False
        padding_length = int(read_first_four)

        read_header = recv_all(conn, 16)
        if not read_header:
            return False
        header = read_header.decode(FORMAT)
        msg_length = int(header.strip())

        message = recv_all(conn, msg_length + padding_length) # frame = header + msg
        if not message:
            return False
        msg = message[0 : msg_length].decode(FORMAT)

        try:
            if int(msg) == code:
                clients.append(conn)
                send(conn, "VERIFICATION COMPLETE")
                print(f"[NEW CONNECTION] Port {addr[1]} connected") 
                print(f"ACTIVE CONNECTIONS: {len(clients)}")
                return True
            
        except ValueError: # If non-numeric values were entered
            pass
        
        print(f"Port {addr[1]} failed verification")
        send(conn, "Incorrect code.")

        if conn in connected:
            connected.remove(conn)

        conn.close()
        return False
    
    finally:
        verifying_limit.release()


def start():
    """
    Listens for incoming client connections. 

    For each new connection, it creates a new thread to handle commmunication between that client and the server and 
    displays the total number of connected clients.
    """
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}")
    
    while True:
        raw_conn, addr = server.accept()
        conn = context.wrap_socket(raw_conn, server_side=True)
        connected.append(conn)

        threading.Thread(target=client_session, args=(conn, addr), daemon=True).start()


def client_session(conn, addr):
    """
    Handles client sessions.
    """
    if not verification(conn, addr):
        return
    handle_client(conn, addr)


def determine_padding(msg_length):
    """
    Slightly tweaked block padding. Randomly chooses a size in SIZES_LIST that is greater than the length of the message. 
    Once chosen, it randomly pads to the size.

    msg_length: length of the message that is to be padded.
    """
    suitable_sizes = [sizes for sizes in SIZES_LIST if sizes > msg_length]
    selected_random_size = random.choice(suitable_sizes)

    num = random.randint(msg_length, selected_random_size) - msg_length - 16 - 5 # Subtract heading and real/dummy heading
    return str(num).zfill(4) # Always fills it to 4 digits. Won't exceed 4, SIZES_LIST caps at 4 digits.


def send(conn, msg):
    """
    Sends bytes to the client. 
    
    Socket exchanges sends specific byte data, so you must know the number of bytes the message you send contains. 
    A workaround is sending a header and a message. The header contains the length of the message, which tells the 
    client the number of bytes the next send (the message) contains.

    conn: The socket object performing the action. Each new connection creates a new socket object which has a unique conn

    msg: Message to be sent
    """
    message = msg.encode(FORMAT) # Converts from strings to bytes to be sent later

    filler = determine_padding(len(msg)).encode(FORMAT)

    header = str(len(message)).encode(FORMAT) 
    header += b' ' * (HEADER - len(header)) # Header is always 16 bytes
    
    frame = "REALL".encode(FORMAT) + filler + header + message
    # frame = filler + header + message
    frame += b' ' * int(filler) # Subtract 

    conn.sendall(frame) # Sends everything


def send_dummy(conn):
    """
    Sends a 5 byte differentiating message, then a 4 byte length message that corresponds to the length of the padding.
    [DUMMY][xxxx][padding]
    """
    message = "DUMMY".encode(FORMAT)
    random_choice = random.choice(SIZES_LIST)
    random_size = random.randint(9, random_choice)
    rand_size_4_digits = str(random_size).zfill(4) # All sizes are fit to 4 digits. For ex, 52 would become 0052

    message = message + rand_size_4_digits.encode(FORMAT)
    message += b' ' * (random_size - 9) # Subtract 9, so the total size is random_size

    conn.sendall(message)


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


def handle_client(conn, addr): # Receive function
    """
    Handles each client's connection to the server. Serves as a receive function for all clients.

    conn: The socket object performing the action. Each new connection creates a new socket object which has a unique conn

    addr: A tuple containing the client's IP and port
    """
    send(conn, f"Connected to {SERVER}") # Sends an initial message to the client that just connected

    while True: # Keeps listening until a client is disconnected

        if conn not in clients: # Ignores nonverified clients.
            break

        gate = recv_all(conn, 5) # Reads the first header to determine whether it's real or dummy traffic

        if not gate:
            pass # Error handling
        elif gate.decode(FORMAT) == "DUMMY": 
            read_first_four = recv_all(conn, 4) # If dummy, it reads the next 4 digits to determine the length of the dummy traffic
            padding_length = int(read_first_four)
            
            recv_all(conn, padding_length - 9) # It then reads the rest of the data and does nothing with it
            continue

        read_first_four = recv_all(conn, 4) # If real traffic, it reads the next 4 bytes which tell the length of the message
        if not read_first_four:
            break
        padding_length = int(read_first_four) 

        read_header = recv_all(conn, 16) # Tells the length of the actual message
        if not read_header:
            break
        header = read_header.decode(FORMAT)
        msg_length = int(header.strip())

        message = recv_all(conn, msg_length + padding_length) # frame = header + msg
        if not message:
            break
        msg = message[0 : msg_length].decode(FORMAT)

        if msg == DISCONNECT_MESSAGE:
            print(f"Port {addr[1]}: {msg}") # Prints which user disconnected to the server
            broadcast(f"Port {addr[1]}: {msg}", conn) 
            break

        print(f"Port {addr[1]}: {msg}") # Prints the message to the server
        broadcast(f"Port {addr[1]}: {msg}", conn) # Broadcasts the message to all other clients.

    print("[DISCONNECTED]")

    if conn in clients:
        clients.remove(conn) 
    # Removes all disconnected clients from the list clients. Exists in a loop to prevent errors where the client might have somehow 
    # already been removed from the list clients.

    print(f"ACTIVE CONNECTIONS: {len(clients)}") # Prints the updated active connections after a client disconnects

    conn.close() # Closes the client's connection.


def broadcast(message, sender=None):
    """
    Broadcasts a message sent by a client to all other clients. 

    message: Message sent by the author

    sender: isn't necessary for this specific function, can be kept for tracking purposes for handle_client function
    """
    for client in clients[:]: # Iterates over a copy of clients list
        if client == sender: # Ignores if the client is the sender, so you will not receive a message from youself
            continue

        try:
            time.sleep(random.expovariate(2))
            send(client, message) # Sends information to every other client, excluding the author of the message
        except:
            clients.remove(client) # Removes the client from the server if they disconnect
            client.close()


def dummy_traffic():
    """
    Creates dummy traffic to the client.
    """
    while True:

        if DUMMY_TRAFFIC != "ON":
            break

        time.sleep(random.expovariate(2))
        for conn in clients[:]: 
            try:
                send_dummy(conn)
            except Exception as e:
                print(f"Dummy send failed: {e}")
                break

threading.Thread(target=dummy_traffic, daemon=True).start()

print("[STARTING] Server is starting...")
start()

