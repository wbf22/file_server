
import os
import sys
import time
import file_server

START_OF_LINE_AND_CLEAR = '\r\033[K'

def test_hashing_big_dir():

    DIR = '~/Documents'


    files = file_server.get_all_files_relative(DIR)

    print()
    start = time.time()
    one_percent = int(len(files) / 100)
    for i, file in enumerate(files):
        file_path = DIR + "/" + file
        file_contents = file_server.read(file_path)
        file_hash = file_server.hash(file_contents)
        # file_server.print_rainbow(file, end='')
        # print(' -> ' + file_hash)
        if i % one_percent == 0:
            percent = i / one_percent
            print(START_OF_LINE_AND_CLEAR + str(percent) + '%', end='')

    print()



    duration = time.time() - start
    print(str(duration) + 's')

    # looks like it takes about 20s to hash my entire documents directory
    # so we should be good for that kind of thing


def make_large_file():
    path = 'client_files/large.md'

    lines = 123456789
    one_percent = int(lines / 100)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Write content to the file
    with open(path, 'w') as file:
        for i in range(lines):
            file.write("I wish for a large file " + str(i) + "\n")
            if i % one_percent == 0:
                percent = i / one_percent
                print(START_OF_LINE_AND_CLEAR + str(percent) + '%', end='')

    print()




make_large_file()