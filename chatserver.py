from sys import argv, stderr, exit

afk_time = 100
config_filename = None
channel_name = []
channel_port = []
channel_capacity = []


def invalid_command_line():
    print("Usage: chatserver [afk_time] config_file\n", file=stderr)
    exit(4)


def invalid_file():
    print("Error: Invalid configuration file.", file=stderr)
    exit(5)


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


def check_valid_file():
    try:
        config_file = open(config_filename, 'r')
    except Exception as e:
        # print(e)  # only for testing
        invalid_file()
    for line in config_file:
        check_file_format(line.strip().split())


def main():
    process_command_line()
    check_valid_file()


if __name__ == "__main__":
    main()
