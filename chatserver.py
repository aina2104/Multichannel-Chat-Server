from sys import argv, stderr, stdout, stdin, exit
from socket import *
from threading import Event, Thread, Lock, current_thread
from time import sleep
import os

lock = Lock()
disconnect_client_lock = Lock()
create_all_ports = Event()
remaining_ports = -1
BUFSIZE = 1024
afk_time = 100
config_filename = None
channel_names = []
channel_port = []
channel_capacity = []
channel_queue_length = []  # not yet implemented
client_info = {}  # {channel_name: {client_username: [client_socket, in-channel/in-queue/disconnected}}
channel_users = {}  # {channel_name: [[user_1, user_2], [user_1_in_queue, user_2_in_queue]]}
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


def is_whitespace(command):
    return len(command.strip()) == 0


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
    if is_whitespace(config_filename):
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
    if not config_file.readline():
        invalid_file()
    config_file.seek(0)
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
    stdout.write(f"Channel \"{name}\" is created on port {port_num}, with a capacity of {capacity}.\n")
    stdout.flush()
    remaining_ports -= 1  # tell program 1 port has been created
    create_all_ports.wait()  # wait until all ports are created to continue
    process_connections(listening_socket, index)  # generate threads per client


def process_connections(listening_socket, index):
    while True:
        client_socket, client_address = listening_socket.accept()
        client_thread = Thread(target=handle_client, 
                            args=(client_socket, client_address, index))
        client_thread.start()


def duplicate_usernames(username, channel_name):
    if any(username in queue for queue in channel_users[channel_name]):
        return True
    return False


# Print to server, send message to client for them to print
def client_join_room(client_username, channel_name, client_socket, code):
    stdout.write(f"[Server Message] {client_username} has joined the channel \"{channel_name}\".\n")
    stdout.flush()
    message = f"$0{code}-JoinSuccess: {channel_name}\n"
    client_socket.sendall(message.encode())


def notify_users_ahead(num_users_ahead, client_socket, code):
    message = f"$0{code}-InQueue: {num_users_ahead}\n"
    client_socket.sendall(message.encode())


# When first accepting client's connection, check for username duplicates, channel capacity,
# queue capacity and return a message that will be sent to client
def client_first_connection(client_username, index, client_address, client_socket):
    global channel_users
    global client_address_users
    channel_name = channel_names[index]
    # Name duplicates
    if duplicate_usernames(client_username, channel_name):
        client_socket.sendall(f"$UserError: {channel_name}\n".encode())
        return False
    # If not error, client info will be stored
    client_address_users[client_address] = [client_username, channel_name]
    capacity = channel_capacity[index]
    # Enough capacity to join successfully
    if len(channel_users[channel_name][0]) < capacity:
        client_join_room(client_username, channel_name, client_socket, code=1)
        channel_users[channel_name][0].append(client_username)
        client_info[channel_name][client_username] = [client_socket, "in-channel"]
    # Wait in queue with X users ahead
    else:
        num_users_ahead = len(channel_users[channel_name][1])
        channel_users[channel_name][1].append(client_username)
        client_info[channel_name][client_username] = [client_socket, "in-queue"]
        notify_users_ahead(num_users_ahead, client_socket, code=1)
    return True


def notify_channel(channel_name, message, kick=False, username=""):
    try:
        if not kick:
            stdout.write(message)
            stdout.flush()
        for other_client_name in channel_users[channel_name][0]:
            if other_client_name == username:
                continue
            client_socket = client_info[channel_name][other_client_name][0]
            client_socket.sendall(message.encode())
    except:
        # print("Error while handling notifying channels", file=stdout)
        pass


def dequeue(channel_name):
    with disconnect_client_lock:
        next_client = channel_users[channel_name][1].pop(0)  # remove first client's name in the queue
        next_client_socket = client_info[channel_name][next_client][0]  # get their socket
        channel_users[channel_name][0].append(next_client)  # add them to the room
        client_info[channel_name][next_client][1] = "in-channel"  # set their status "in-channel"
        client_join_room(next_client, channel_name, next_client_socket, code=2)  # server and joined client will print msg to the terminal


# disconnect -> notify channel -> join room/notify users
def disconnect_client(channel_name, username, client_socket, index, kick=False, AFK=False):
    if client_info[channel_name][username][1] == "disconnected":
        return
    client_socket.close()
    if kick:
        stdout.write(f"[Server Message] Kicked {username}.\n")
        stdout.flush()
    if client_info[channel_name][username][1][:10] == "in-channel":  # [:10] in case they are muted
            channel_users[channel_name][0].remove(username) # remove a specific client in the room
            if not AFK:
                left_notification(username, channel_name, kick=kick)
            capacity = channel_capacity[index]
            position = 0
            # check queue and notify people in the queues
            if len(channel_users[channel_name][0]) < capacity and len(channel_users[channel_name][1]) > 0:
                dequeue(channel_name)
    # if remove people in queue, notify the one after (find the index of the removed one)
    else:
        position = channel_users[channel_name][1].index(username)
        channel_users[channel_name][1].remove(username)
    # notify others in the queue
    client_info[channel_name][username][1] = "disconnected"
    for pos in range(position, len(channel_users[channel_name][1])):
        other_client_name = channel_users[channel_name][1][pos]
        other_client_socket = client_info[channel_name][other_client_name][0]
        notify_users_ahead(pos, other_client_socket, code=2)


def timeout_notification(username, channel_name):
    message = f"[Server Message] {username} went AFK in channel \"{channel_name}\".\n"
    notify_channel(channel_name, message)


def left_notification(username, channel_name, kick=False):
    with disconnect_client_lock:
        left_channel_msg = f"[Server Message] {username} has left the channel.\n"
        notify_channel(channel_name, left_channel_msg, kick=kick)


def list_channels(client_socket):
    list_message = ""
    for i, channel in enumerate(channel_names):
        port = channel_port[i]
        capacity = channel_capacity[i]
        current_capacity = len(channel_users[channel][0])
        in_queue = len(channel_users[channel][1])
        list_message = f"[Channel] {channel} {port} Capacity: {current_capacity}/{capacity}, Queue: {in_queue}\n"
        client_socket.sendall(list_message.encode())


def check_switch_command(line, username, client_socket):
    command = line.split()
    channel_name = command[1]
    if channel_name not in channel_names:
        client_socket.sendall(f"[Server Message] Channel \"{channel_name}\" does not exist.\n".encode())
    elif duplicate_usernames(username, channel_name):
        client_socket.sendall(f"$UserDup: {channel_name}\n".encode())


def check_send_command(line, client_socket, channel_name):
    command = line.split()
    target_username = command[1]
    if target_username not in channel_users[channel_name][0]:
        client_socket.sendall(f"[Server Message] {target_username} is not in the channel.\n".encode())


def check_whisper_command(line, client_socket, channel_name, username):
    command = line.split()
    target_username = command[1]
    chat_message = command[2]
    if target_username != username:
        if target_username not in channel_users[channel_name][0]:
            client_socket.sendall(f"[Server Message] {target_username} is not in the channel.\n".encode())
            return
        receiver_socket = client_info[channel_name][target_username][0]  # get receiver info if in the channel
        receiver_socket.sendall(f"[{username} whispers to you] {chat_message}\n".encode())
        client_socket.sendall(f"[{username} whispers to {target_username}] {chat_message}\n".encode())
    stdout.write(f"[{username} whispers to {target_username}] {chat_message}\n")
    stdout.flush()


# REF: The use of socket.settimeout() is inspired by the code at
# REF: https://stackoverflow.com/questions/34371096/how-to-use-python-socket-settimeout-properly
def handle_client(client_socket, client_address, index):
    duplication = False
    with client_socket:
        try:
            while data := client_socket.recv(BUFSIZE).decode():
                # print(f"Message at client_socket: {message}", file=stdout)
                with lock:
                    while "\n" in data:
                        newline_index = data.index("\n")
                        message = data[:(newline_index+1)]
                        data = data[(newline_index+1):]
                        if message[:6] == "$User:":
                            username = message[:-1][7:]
                            channel_name = channel_names[index]
                            if not client_first_connection(message[:-1][7:], index, client_address, client_socket):
                                duplication = True
                        elif message[:5] == "$Quit":
                            kicked = True if message[:-1][6:] == "kicked" else False
                            disconnect_client(channel_name, username, client_socket, index, kick=kicked)
                        elif message == "$List\n":
                            list_channels(client_socket)
                        elif message[:7] == "/switch":
                            check_switch_command(message, username, client_socket)
                        elif client_info[channel_name][username][1][:16] == "in-channel-muted":
                            duration = client_info[channel_name][username][1][17:]
                            client_socket.sendall(f"[Server Message] You are still in mute for {duration} seconds.\n".encode())
                        elif message[:5] == "/send":
                            check_send_command(message, client_socket, channel_name)
                        elif message[:8] == "/whisper":
                            check_whisper_command(message, client_socket, channel_name, username)
                        elif message[0] != "$" and message[0] != "/":
                            if client_info[channel_name][username][1] == "in-channel":  # if not muted
                                username, channel_name = client_address_users[client_address]
                                to_send = f"[{username}] {message}" # message already includes \n
                                notify_channel(channel_name, to_send)
                        if client_info[channel_name][username][1] == "in-channel":  # if not muted
                            client_socket.settimeout(afk_time)
        except TimeoutError:
            # also send this to all clients in the channel
            timeout_notification(username, channel_name)
            client_socket.sendall("$AFK\n".encode())
            disconnect_client(channel_name, username, client_socket, index, AFK=True)
        except Exception:
            # print(f"Message at Exception: {message}", file=stdout)
            if message[:5] != "$Quit":
                disconnect_client(channel_name, username, client_socket, index, kick=False)
            # print(f"Connection from {username} closed.")
    # error or EOF - client disconnected
    if duplication:
        client_socket.close()
    else:
        disconnect_client(channel_name, username, client_socket, index, kick=False)  # abruptly closed


# REF: The use of os._exit() is inspired by the code at
# REF: https://stackoverflow.com/questions/1489669/how-to-exit-the-entire-application-from-a-python-thread
def server_shutdown(command):
    if not (command == "/shutdown" or command == "\n"):
        stdout.write("Usage: /shutdown\n")
        stdout.flush()
        return
    stdout.write("[Server Message] Server shuts down.\n")
    stdout.flush()
    os._exit(0)


def channel_exists(channel_name):
    if channel_name not in channel_names:
        stdout.write(f"[Server Message] Channel \"{channel_name}\" does not exist.\n")
        stdout.flush()
        return False
    return True


def client_not_in_channel(client_username, channel_name):
    if client_username not in channel_users[channel_name][0]:
        stdout.write(f"[Server Message] {client_username} is not in the channel.\n")
        stdout.flush()
        return True
    return False


def kick(orig_command):
    command = orig_command.split()
    if len(command) != 3 or orig_command.count(" ") != 2:
        stdout.write("Usage: /kick channel_name client_username\n")
        stdout.flush()
        return
    channel_name = command[1]
    client_username = command[2]
    if not channel_exists(channel_name):
        return
    if client_not_in_channel(client_username, channel_name):
        return
    # If the command is valid, kick!
    client_socket = client_info[channel_name][client_username][0]
    # Sending the message below will make client sends a "$Quit" message, the socket will then be disconnected
    # handling by Exception catch in handle_client() - maybe should not do this
    client_socket.sendall("$Kick\n".encode())


def empty(line):
    command = line.split()
    if len(command) != 2 or line.count(" ") != 1:
        stdout.write("Usage: /empty channel_name\n")
        stdout.flush()
        return
    channel_name = command[1]
    if not channel_exists(channel_name):
        return
    for client_username in channel_users[channel_name][0]:
        client_socket = client_info[channel_name][client_username][0]
        client_socket.sendall("$Empty\n".encode())
        client_socket.close()
        client_info[channel_name][client_username][1] = "disconnected"
    stdout.write(f"[Server Message] \"{channel_name}\" has been emptied.\n")
    stdout.flush()
    channel_users[channel_name][0] = []
    capacity = channel_capacity[channel_names.index(channel_name)]
    while len(channel_users[channel_name][0]) < capacity and len(channel_users[channel_name][1]) > 0:
        dequeue(channel_name)


def mute(line):
    command = line.split()
    if len(command) != 4 or line.count(" ") != 3:
        stdout.write("Usage: /mute channel_name client_username duration\n")
        stdout.flush()
        return
    channel_name = command[1]
    if not channel_exists(channel_name):
        return
    client_username = command[2]
    if client_not_in_channel(client_username, channel_name):
        return
    duration = command[3]
    if not duration.isdigit() or int(duration) <= 0:
        stdout.write("[Server Message] Invalid mute duration.\n")
        stdout.flush()
        return
    client_info[channel_name][client_username][1] = f"in-channel-muted-{duration}"
    stdout.write(f"[Server Message] Muted {client_username} for {duration} seconds.\n")
    stdout.flush()
    client_socket = client_info[channel_name][client_username][0]
    client_socket.sendall(f"[Server Message] You have been muted for {duration} seconds.\n".encode())
    message = f"[Server Message] {client_username} has been muted for {duration} seconds.\n"
    notify_channel(channel_name, message, kick=True, username=client_username)  # kick=True to avoid server to print again


# REF: The use of Event and their function set(), wait() is inspired by the code at
# REF: https://www.instructables.com/Starting-and-Stopping-Python-Threads-With-Events-i/
if __name__ == "__main__":
    process_command_line()
    check_valid_file()
    # print(channel_names)
    # print(channel_port)
    # print(channel_capacity)
    remaining_ports = len(channel_port)  # will be decrement to check finished port
    channels = [None] * remaining_ports  # store the socket object?
    listening_threads = [None] * remaining_ports  # don't think I need this
    channel_users = {each_channel: [[],[]] for each_channel in channel_names}  # check duplicate users in each channel
    client_info = {each_channel: {} for each_channel in channel_names}
    # Thread per listening socket
    for index, port_num in enumerate(channel_port):
        listening_thread = Thread(target=start_server, args=(port_num, index))
        listening_thread.start()
    while remaining_ports > 0:
        pass
    stdout.write("Welcome to chatserver.\n")
    stdout.flush()
    create_all_ports.set()  # all channels start accepting connections

    # Main thread starts reading from stdin
    try:
        while line := input():
            with lock:
                if line == "\n" or line[:9] == "/shutdown":
                    server_shutdown(line)
                elif line[:5] == "/kick":
                    kick(line)
                elif line[:6] == "/empty":
                    empty(line)
                elif line[:5] == "/mute":
                    mute(line)
    except Exception as e:
        # print(e)
        pass
    # print("Server is disconnected.", file=stdout)