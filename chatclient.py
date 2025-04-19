from sys import argv, stderr, stdout, stdin, exit
from socket import *

BUFSIZE = 1024

port_number = None
client_username = None


def invalid_command_line():
    print("Usage: chatclient port_number client_username\n", file=stderr)
    exit(3)


def cant_connect(port_num):
    print(f"Error: Unable to connect to port {port_num}.\n")
    exit(7)


def username_error(channel_name):
    print(f"[Server Message] Channel {channel_name} already has user"
          f"{client_username}.\n", file=stdout)
    exit(2)


def process_command_line():
    global client_username
    if len(argv) != 3:
        invalid_command_line()
    if argv[1] == "" or argv[2] == "":
        invalid_command_line()
    client_username = argv[2]


def port_checking():
    global port_number
    if not argv[1].isdigit():
        cant_connect(argv[1])
    port_number = int(argv[1])
    if port_number < 1024 or port_number > 65535:
        cant_connect(port_number)


if __name__ == "__main__":
    process_command_line()
    port_checking()
    # Main thread to read from stdin
    sock = socket(AF_INET, SOCK_STREAM)
    try:
        sock.connect(('localhost', port_number))
    except Exception:
        cant_connect(port_number)
    for line in stdin:
        sock.send(line.encode())
        data = sock.recv(BUFSIZE)
        if not data:
            break
        stdout.buffer.write(data)
        stdout.flush()