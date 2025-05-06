from sys import argv, stderr, stdout, stdin, exit
from socket import *
from threading import Thread, Event
import os

BUFSIZE = 1024

port_number = None
client_username = None
server_connected = None
exit_status = Event()
status = None


def invalid_command_line():
    print("Usage: chatclient port_number client_username", file=stderr)
    exit(3)


def cant_connect(port_num):
    print(f"Error: Unable to connect to port {port_num}.", file=stderr)
    exit(7)


# REF: The use of os._exit() is inspired by the code at
# REF: https://stackoverflow.com/questions/1489669/how-to-exit-the-entire-application-from-a-python-thread
def username_error(channel_name):
    stdout.write(f"[Server Message] Channel \"{channel_name}\" already has user {client_username}.\n")
    stdout.flush()


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


def check_command_list(command, server_socket):
    if command != "/list\n":
        stdout.write("[Server Message] Usage: /list\n")
        stdout.flush()
    else:
        server_socket.sendall("$List\n".encode())


def check_command_switch(line, server_socket):
    command = line.split()
    if len(command) != 2 or line.count(" ") != 1:
        stdout.write("[Server Message] Usage: /switch channel_name\n")
        stdout.flush()
    else:
        server_socket.sendall(line.encode())


def check_command_send(line, server_socket):
    if status == "in-queue":
        return
    command = line.split()
    if len(command) != 3 or line.count(" ") != 2:
        stdout.write("[Server Message] Usage: /send target_client_username file_path\n")
        stdout.flush()
        return
    target_username = command[1]
    if target_username == client_username:
        stdout.write("[Server Message] Cannot send file to yourself.\n")
        stdout.flush()
        return
    server_socket.sendall(line.encode())


def check_command_whisper(line, server_socket):
    if status == "in-queue":
        return
    command = line.split()
    if len(command) != 3 or line.count(" ") != 2:
        stdout.write("[Server Message] Usage: /whisper receiver_client_username chat_message\n")
        stdout.flush()
        return
    target_username = command[1]
    chat_message = command[2]  # this does not include "\n"
    if target_username == client_username:  # whispers to self
        stdout.write(f"[{client_username} whispers to you] {chat_message}\n")
        stdout.flush()
    server_socket.sendall(line.encode())


# A 2nd thread to continuously read data sent from server
def read_from_stdin(server_socket):
    global server_connected
    server_connected.wait()
    try:
        for line in stdin:
            if line == "\n" or line == "/quit\n":
                server_socket.send("$Quit\n".encode())
                quit()
            elif line[:5] == "/quit":
                stdout.write("[Server Message] Usage: /quit\n")
                stdout.flush()
            elif line[:5] == "/list":
                check_command_list(line, server_socket)
            elif line[:7] == "/switch":
                check_command_switch(line, server_socket)
            elif line[:5] == "/send":
                check_command_send(line, server_socket)
            elif line[:8] == "/whisper":
                check_command_whisper(line, server_socket)
            elif line[0] != "/" and line[0] != "$":
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
        stdout.write(f"[Server Message] You have joined the channel \"{message[17:]}\".\n")
        stdout.flush()
        server_socket.sendall("$Joined\n".encode())
        status = "in-channel"
    elif message[4:12] == "InQueue:":
        stdout.write(f"[Server Message] You are in the waiting queue and there are {message[13:]} user(s) ahead of you.\n")
        stdout.flush()
        status = "in-queue"


def removed(server_socket):
    stdout.write("[Server Message] You are removed from the channel.\n")
    stdout.flush()
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
        user_msg = f"$User: {client_username}\n"
        server_socket.send(user_msg.encode())
    except Exception:
        cant_connect(port_number)

    # A thread to read from stdin
    server_thread = Thread(target=read_from_stdin, args=(server_socket,))
    server_thread.start()

    # Main thread to read from server
    with server_socket:
        try:
            while message := server_socket.recv(BUFSIZE).decode():
                while "\n" in message:
                    newline_index = message.index("\n")
                    data = message[:(newline_index+1)]
                    message = message[(newline_index+1):]
                    if data[:10] == "$UserError":
                        username_error(data[:-1][12:])
                        os._exit(2)
                    elif data[:8] == "$UserDup":
                        username_error(data[:-1][10:])
                    elif data[:4] == "$01-" or data[:4] == "$02-":
                        channel_connected(data[:-1], server_socket)
                        server_connected.set()
                    elif data == "$Kick\n":
                        server_socket.sendall("$Quit-kicked\n".encode())
                        removed(server_socket)
                    elif data == "$Empty\n":
                        # server_socket.sendall(data.encode())
                        removed(server_socket)
                    elif data == "$AFK\n":
                        quit()
                    elif data[0] != "$":
                        stdout.write(data)
                        stdout.flush()
                    # server_socket.sendall(data.encode())
        except Exception:
            print("Error: server connection closed.", file=stderr)
            os._exit(8)
    print("Error: server connection closed.", file=stderr)
    os._exit(8)