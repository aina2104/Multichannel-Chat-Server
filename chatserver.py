from sys import argv, stderr, stdout, stdin, exit
from socket import *
from threading import Event, Thread, current_thread
from time import sleep
import os

create_all_ports = Event()
remaining_ports = -1
BUFSIZE = 1024
afk_time = 100
config_filename = None
channel_names = []
channel_port = []
channel_capacity = []
channel_queue_length = []  # not yet implemented
client_info = {}  # {client_username: client_socket}
channel_users = {}  # {channel_names: [[user_1, user_2], [user_1_in_queue, user_2_in_queue]]}
client_address_users = {}  # {client_address: [client_username, channel_name]}


def invalid_command_line():
    print("Usage: chatserver [afk_time] config_file", file=stderr)
    exit(4)


def invalid_file():
    print("Error: Invalid configuration file.", file=stderr)
    exit(5)


def cant_listen(port_num):
    print(f"Error: unable to listen on port {port_num}.", file=stderr)
    exit(6)  # maybe have to wait until all unlistened port error msg are printed before exiting


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
    global channel_names
    global channel_port
    global channel_capacity
    if len(line) != 4 or line[0] != "channel":
        invalid_file()
    check_channel_name(line[1])
    if not (line[2].isdigit() and line[3].isdigit()):
        invalid_file()
    port, capacity = int(line[2]), int(line[3])
    if (port < 1024 or port > 65535 or capacity < 1 or capacity > 8 or
            line[1] in channel_names or port in channel_port):
        invalid_file()
    channel_names.append(line[1])
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
    global remaining_ports
    name = channel_names[index]
    capacity = channel_capacity[index]

    listening_socket = socket(AF_INET, SOCK_STREAM)
    # set socket option to allow the reuse of address
    listening_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    try:
        listening_socket.bind(('', port_num))
    except Exception:
        cant_listen(port_num)
    listening_socket.listen(5)
    print(f"Channel \"{name}\" is created on port {port_num}, with a capacity"
          f" of {capacity}.", flush=True)
    remaining_ports -= 1  # tell program 1 port has been created
    create_all_ports.wait()  # wait until all ports are created to continue
    process_connections(listening_socket, index)  # generate threads per client


def duplicate_usernames(username, channel_name):
    if any(username in queue for queue in channel_users[channel_name]):
        return True
    return False


# When first accepting client's connection, check for username duplicates, channel capacity,
# queue capacity and return a message that will be sent to client
def client_first_connection(client_username, index, client_address, client_socket):
    global channel_users
    global client_address_users
    channel_name = channel_names[index]
    # Name duplicates
    if duplicate_usernames(client_username, channel_name):
        return f"$UserError: {channel_name}"
    # If not error, client info will be stored
    client_address_users[client_address] = [client_username, channel_name]
    client_info[client_username] = client_socket
    capacity = channel_capacity[index]
    # Enough capacity to join successfully
    if len(channel_users[channel_name][0]) < capacity:
        channel_users[channel_name][0].append(client_username)
        print(f"[Server Message] {client_username} has joined the channel \"{channel_name}\".", file=stdout)
        return f"$01-JoinSuccess: {channel_name}"
    # Wait in queue with X users ahead
    num_users_ahead = len(channel_users[channel_name][1])
    channel_users[channel_name][1].append(client_username)
    return f"$01-InQueue: {num_users_ahead}"


# Close connection of a client from a channel, if client is in the room,
# remove them and push any client waiting in the queue.
# If client in the queue, remove from the queue.
def remove_from_channel(client_username, channel_name):
    # Only implement the queue
    pass


def notify_channel(channel_name, message):
    try:
        print(message, file=stdout)
        for other_client_name in channel_users[channel_name][0]:
            client_socket = client_info[other_client_name]
            client_socket.sendall(message.encode())
    except:
        print("Error while handling notifying channels", file=stdout)


# REF: The use of socket.settimeout() is inspired by the code at
# REF: https://stackoverflow.com/questions/34371096/how-to-use-python-socket-settimeout-properly
def handle_client(client_socket, client_address, index):
    with client_socket:
        try:
            client_socket.settimeout(afk_time)
            while message := client_socket.recv(BUFSIZE).decode():
                if message[:6] == "$User:":
                    message = client_first_connection(message[7:], index, client_address, client_socket)
                    username, channel_name = client_address_users[client_address]
                    client_socket.sendall(message.encode())
                else:
                    username, channel_name = client_address_users[client_address]
                    to_send = f"[{username}] {message}"
                    notify_channel(channel_name, to_send)
        except timeout:
            # also send this to all clients in the channel
            message = f"[Server Message] {username} went AFK in channel \"{channel_name}\"."
            channel_users[channel_name][0].remove(username)
            client_socket.close()
            notify_channel(channel_name, message)
        except Exception:
            # close the client's connection if they abruptly close
            if message[:10] != "$UserError":
                print(f"Connection from {username} closed.")
            client_socket.close()  # server handles closing client's socket.
    # error or EOF - client disconnected


def process_connections(listening_socket, index):
    while True:
        client_socket, client_address = listening_socket.accept()
        client_thread = Thread(target=handle_client, 
                            args=(client_socket, client_address, index))
        client_thread.start()


# REF: The use of os._exit() is inspired by the code at
# REF: https://stackoverflow.com/questions/1489669/how-to-exit-the-entire-application-from-a-python-thread
def server_shutdown():
    print("[Server Message] Server shuts down.")
    os._exit(0)


# REF: The use of Event and their function set(), wait() is inspired by the code at
# REF: https://www.instructables.com/Starting-and-Stopping-Python-Threads-With-Events-i/
if __name__ == "__main__":
    process_command_line()
    check_valid_file()
    print(channel_names)
    print(channel_port)
    print(channel_capacity)
    remaining_ports = len(channel_port)  # will be decrement to check finished port
    channels = [None] * remaining_ports  # store the socket object?
    listening_threads = [None] * remaining_ports  # don't think I need this
    channel_users = {each_channel: [[],[]] for each_channel in channel_names}  # check duplicate users in each channel
    # Thread per listening socket
    for index, port_num in enumerate(channel_port):
        listening_thread = Thread(target=start_server, args=(port_num, index))
        listening_thread.start()
    while remaining_ports > 0:
        pass
    print("Welcome to chatserver.", flush=True)
    create_all_ports.set()  # all channels start accepting connections

    # Main thread starts reading from stdin
    try:
        while line := input():
            if line == "/shutdown":
                server_shutdown()
    except Exception:
        pass
    print("Server is disconnected.", file=stdout)
