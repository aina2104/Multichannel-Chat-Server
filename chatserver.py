from sys import argv, stderr, stdout, exit
from socket import *
from threading import Event, Lock, Thread, current_thread
from time import sleep

create_all_ports = Event()
remaining_ports = -1
counter = 0
counter_lock = Lock()
BUFSIZE = 1024
afk_time = 100
config_filename = None
channels = []
channel_name = []
channel_port = []
channel_capacity = []


def invalid_command_line():
    print("Usage: chatserver [afk_time] config_file\n", file=stderr)
    exit(4)


def invalid_file():
    print("Error: Invalid configuration file.\n", file=stderr)
    exit(5)


def cant_listen(port_num):
    print(f"Error: unable to listen on port {port_num}.\n")
    exit(6)


def process_command_line():
    global afk_time
    global config_filename
    if len(argv) != 2 and len(argv) != 3:
        invalid_command_line()
    if len(argv) == 3:
        if not argv[1].isdigit():
            invalid_command_line()
        if int(argv[1]) < 1 or int(argv[1]) > 1000:
            invalid_command_line()
        afk_time = int(argv[1])
        config_filename = argv[2]
    else:
        config_filename = argv[1]
    if config_filename == "":
        invalid_command_line()


def check_channel_name(name):
    for letter in name:
        if not (letter.isalpha() or letter.isdigit() or letter == "_"):
            invalid_file()


def check_file_format(line):
    global channel_name
    global channel_port
    global channel_capacity
    if len(line) != 4 or line[0] != "channel":
        invalid_file()
    check_channel_name(line[1])
    if not (line[2].isdigit() and line[3].isdigit()):
        invalid_file()
    port, capacity = int(line[2]), int(line[3])
    if (port < 1024 or port > 65535 or capacity < 1 or capacity > 8 or
            line[1] in channel_name or port in channel_port):
        invalid_file()
    channel_name.append(line[1])
    channel_port.append(port)
    channel_capacity.append(capacity)


def check_valid_file():
    try:
        config_file = open(config_filename, 'r')
    except Exception:
        # print(e)  # only for testing
        invalid_file()
    for line in config_file:
        check_file_format(line.strip().split())


def start_server(port_num, index):
    global channels
    global remaining_ports
    name = channel_name[index]
    capacity = channel_capacity[index]

    listening_socket = socket(AF_INET, SOCK_STREAM)
    # set socket option to allow the reuse of address
    listening_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    try:
        listening_socket.bind(('', port_num))
    except Exception:
        cant_listen(port_num)
    listening_socket.listen(5)
    # channels.insert(index, listening_socket)
    print(f"Channel \"{name}\" is created on port {port_num}, with a capacity"
          f" of {capacity}.\n", flush=True)
    remaining_ports -= 1  # tell program 1 port has been created
    create_all_ports.wait()  # wait until all ports are created to continue
    process_connections(listening_socket)


def handle_client(client_socket, client_address):
    global counter
    host,_ = getnameinfo(client_address, 0)
    print(f"Connection from {client_address} ({host}) has been established.")
    with client_socket:
        # Send a message to the client
        message = f"Welcome to the service.\n"
        client_socket.sendall(message.encode())

        while data := client_socket.recv(BUFSIZE):
            # Locking the shared resource (counter)
            with counter_lock:
                print(f"Thread {current_thread().name} got the lock.")
                counter += 1
                print(f"Counter value updated to: {counter}")
                # Simulate doing some work
                sleep(2)
                data = data.decode().upper() 
                client_socket.sendall(data.encode())
        # error or EOF - client disconnected

    print(f"Connection from {client_address} closed.")


def process_connections(listening_socket):
    while True:
        client_socket, client_address = listening_socket.accept()
        client_thread = Thread(target=handle_client, 
                            args=(client_socket, client_address))
        client_thread.start()


# REF: The use of Event and their function set(), wait() is inspired by the code at
# REF: https://www.instructables.com/Starting-and-Stopping-Python-Threads-With-Events-i/
if __name__ == "__main__":
    process_command_line()
    check_valid_file()
    print(channel_name)
    print(channel_port)
    print(channel_capacity)
    remaining_ports = len(channel_port)  # will be decrement to check finished port
    channels = [None] * remaining_ports  # store the socket object?
    listening_threads = [None] * remaining_ports  # don't think I need this
    # Thread per listening socket
    for index, port_num in enumerate(channel_port):
        listening_thread = Thread(target=start_server, 
                args=(port_num, index))
        listening_thread.start()
    while remaining_ports > 0:
        pass
    print("Welcome to chatserver.", flush=True)
    create_all_ports.set()
