from sys import argv, stderr, stdout, stdin, exit
from socket import *
from threading import Thread, Event
import os

BUFSIZE = 1024

port_number = None
client_username = None
server_connected = None
exit_status = Event()


def invalid_command_line():
    print("Usage: chatclient port_number client_username", file=stderr)
    exit(3)


def cant_connect(port_num):
    print(f"Error: Unable to connect to port {port_num}.", file=stderr)
    exit(7)


# REF: The use of os._exit() is inspired by the code at
# REF: https://stackoverflow.com/questions/1489669/how-to-exit-the-entire-application-from-a-python-thread
def username_error(channel_name):
    print(f"[Server Message] Channel \"{channel_name}\" already has user {client_username}.", file=stdout)
    os._exit(2)


def quit():
    os._exit(0)


def is_whitespace(command):
    return len(command.strip()) == 0 or " " in command


def process_command_line():
    global client_username
    if len(argv) != 3:
        invalid_command_line()
    if is_whitespace(argv[1]) or is_whitespace(argv[2]):
        invalid_command_line()
    client_username = argv[2]


def port_checking():
    global port_number
    if not argv[1].isdigit():
        cant_connect(argv[1])
    port_number = int(argv[1])
    if port_number < 1024 or port_number > 65535:
        cant_connect(argv[1])


# A 2nd thread to continuously read data sent from server
def read_from_stdin(server_socket):
    global server_connected
    server_connected.wait()
    try:
        for line in stdin:
            if line == "/quit\n":
                server_socket.send("$Quit".encode())
                quit()
            if line == "/k\n":
                quit()
            server_socket.send(line.encode())
            # data = server_socket.recv(BUFSIZE).decode()
            # stdout.buffer.write(data)
            # stdout.flush()
    except Exception as e:
        # print("Reached Exception", file=stdout)
        # print(e, file=stdout)
        pass
    # print("You are disconnected.", file=stdout)


# Client Runtime Behaviour - when clients successfully connected to the channel
def channel_connected(message, server_socket):
    if data[:4] == "$01-":
        print(f"Welcome to chatclient, {client_username}.")
    if message[4:16] == "JoinSuccess:":
        print(f"[Server Message] You have joined the channel \"{message[17:]}\".", flush=True)
        server_socket.sendall("$Joined".encode())
    elif message[4:12] == "InQueue:":
        print(f"[Server Message] You are in the waiting queue and there are {message[13:]} user(s) ahead of you.", flush=True)


def removed(server_socket):
    print("[Server Message] You are removed from the channel.", flush=True)
    server_socket.close()
    quit()


# REF: The use of Event and their function set(), wait() is inspired by the code at
# REF: https://www.instructables.com/Starting-and-Stopping-Python-Threads-With-Events-i/
if __name__ == "__main__":
    process_command_line()
    port_checking()
    server_connected = Event()
    
    # Connect to server
    server_socket = socket(AF_INET, SOCK_STREAM)
    try:
        server_socket.connect(('localhost', port_number))
        # as soon as connections accepted, send server the username
        user_msg = f"$User: {client_username}"
        server_socket.send(user_msg.encode())
    except Exception:
        cant_connect(port_number)

    # A thread to read from stdin
    server_thread = Thread(target=read_from_stdin, args=(server_socket,))
    server_thread.start()

    # Main thread to read from server
    with server_socket:
        try:
            while data := server_socket.recv(BUFSIZE).decode():
                if data[:10] == "$UserError":
                    username_error(data[12:])
                if data[:4] == "$01-" or data[:4] == "$02-":
                    channel_connected(data, server_socket)
                    server_connected.set()
                elif data == "$Kick":
                    server_socket.sendall("$Quit-kicked".encode())
                    removed(server_socket)
                elif data == "$Empty":
                    # server_socket.sendall(data.encode())
                    removed(server_socket)
                elif data == "$AFK":
                    quit()
                else:
                    print(data[:-1], flush=True)
                # server_socket.sendall(data.encode())
        except Exception:
            # print("Error: server connection closed.", file=stderr)
            os._exit(8)
    