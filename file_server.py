import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import http
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
import socket
import subprocess
from typing import Dict, List
from urllib.parse import urlparse

import concurrent



DIRECTORY = 'files'
PASSWORD = ''

URL = None
PORT = 8000

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
SIZE_LIMIT = 10000 * 64 # 10,000 lines of 64 chars
FILE_TOO_LARGE = 'FILE_TOO_LARGE'

RED = '\x1b[38;2;255;0;0m'
ORANGE = '\x1b[38;2;230;76;0m'
YELLOW = '\x1b[38;2;230;226;0m'
GREEN = '\x1b[38;2;0;186;40m'
BLUE = '\x1b[38;2;0;72;255m'
INDIGO = '\x1b[38;2;84;0;230m'
VIOLET = '\x1b[38;2;176;0;230m'
ANSII_RESET = '\x1b[0m'
STRIKE = '\033[9m'
START_OF_LINE_AND_CLEAR = '\r\033[K'

SHRUG = '¯\_(ツ)_/¯'
NICE = '(☞ﾟヮﾟ)☞'
NICE_OTHER = '☜(ﾟヮﾟ☜)'
TABLE_FLIP = '(╯°□°）╯︵ ┻━┻'
PUT_TABLE_BACK = '┬─┬ ノ( ゜-゜ノ)'
WAVING = '(°▽°)/'


# UTIL FUNCTION
def get_all_files_relative(directory: str) -> List[str]:
    directory = os.path.expanduser(directory)
    files_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Create absolute or relative path as needed
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, directory)
            files_list.append(relative_path)
    return files_list

def print_dir_structure(files_list: List[str]):
    tree = {}
    for path in files_list:
        parts = path.split(os.sep)
        current_level = tree
        for part in parts:
            current_level = current_level.setdefault(part, {})

    def print_tree(current_dict, indent=""):
        items = sorted(current_dict.items())
        for i, (name, subdict) in enumerate(items):
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            print(indent + connector + name)
            next_indent = indent + ("    " if is_last else "│   ")
            print_tree(subdict, next_indent)

    print_tree(tree)

def hash(file_path: str, algorithm: str = 'sha256', chunk_size: int = 1024 * 1024) -> str:
    hash_func = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hash_func.update(chunk)
    return hash_func.hexdigest()

def read(file_path: str) -> str:
    file_path = os.path.expanduser(file_path)
    with open(file_path, 'rb') as file:
        return base64.b64encode(file.read()).decode('utf-8')
    
def get_file_last_modified(file_path: str) -> datetime:
    # Get the timestamp of last modification
    timestamp = os.path.getmtime(file_path)
    # Convert timestamp to a datetime object
    return datetime.fromtimestamp(timestamp)

def write_file_with_dirs(file_path, binary_data, open_arg='wb'):
    # Ensure parent directories exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    # Write content to the file
    with open(file_path, open_arg) as file:
        file.write(binary_data)

def parse_url(url: str):
    # parsed_url = urlparse(url)
    scheme = 'https' if url.startswith("https") else 'http'
    i = 0
    if url.startswith('http'):
        i = 4
        while url[i] != '/' and url[i-1] != '/':
            i += 1
    
    start = i
    while i < len(url) and url[i] != ':' and url[i] != '/':
        i += 1
    host = url[start:i]

    port = ''
    if i < len(url) and url[i] == ':':
        start = i + 1
        while i < len(url) and url[i] != '/':
            i += 1
        port = url[start:i]
    
    path = url[i:]

    conn_class = http.client.HTTPSConnection if scheme == 'https' else http.client.HTTPConnection
    if port is None:
        port = 443 if scheme == 'https' else 80

    return host, port, path, conn_class

def call(url: str, method: str, body: any, headers={'Content-type': 'application/json'}, timeout=10) -> list[int, any]:

    if headers is None:
        headers = {}
    headers['Content-Type'] = 'application/json'
    

    redirect_count = 0
    current_url = url

    while redirect_count < 10:
        
        # parse host and make request
        host, port, path, conn_class = parse_url(current_url)
        conn = conn_class(host, port, timeout=timeout)

        if body != None:
            payload = json.dumps(body)
            conn.request(method, path, body=payload, headers=headers)
        else:
            conn.request(method, path, headers=headers)

        response = conn.getresponse()

        # handle redirects
        if response.status in (301, 302, 303, 307, 308):
            location = response.getheader('Location')
            if not location:
                break
            current_url = location
            conn.close()
            redirect_count += 1
            continue
        else:
            # process response
            res_body = response.read().decode()
            conn.close()
            return response.status, json.loads(res_body) if res_body else {}
    # Too many redirects
    raise Exception("Too many redirects")

def get(url: str, headers={}, timeout=10) -> list[int, any]:
    return call(url, 'GET', None, headers, timeout=timeout)

def post(url: str, body: any, headers={'Content-type': 'application/json'}, timeout=10) -> list[int, any]:
    return call(url, 'POST', body, headers, timeout=timeout)

def chunked_file_upload(url: str, file_path: str, method: str, headers={'Content-type': 'application/octet-stream', 'Transfer-Encoding': 'chunked'}, timeout=10):
    
    host, port, path, conn_class = parse_url(url)
    conn = conn_class(host, port, timeout=timeout)
    conn.putrequest(method, path)
    headers['Content-type'] = 'application/octet-stream'
    headers['Transfer-Encoding'] = 'chunked'
    for key, value in headers.items():
        conn.putheader(key, value)
    conn.endheaders()

    file_size = os.path.getsize(file_path)
    i_sent = 0
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(1024*1024)  # 1MB chunks
            if not chunk:
                break
            # Send chunk size in hex
            conn.send(f"{len(chunk):X}\r\n".encode('utf-8'))
            # Send chunk data
            conn.send(chunk)
            conn.send(b"\r\n")

            i_sent += 1024*1024
            print(START_OF_LINE_AND_CLEAR + file_path + ' --> ' + str(100 * i_sent / file_size) + '%', end='')
    print(START_OF_LINE_AND_CLEAR, end='')

    # Send zero-length chunk to indicate end
    conn.send(b"0\r\n\r\n")

    response = conn.getresponse()

    res_body = response.read().decode()
    conn.close()
    return response.status, json.loads(res_body) if res_body else {}

def chunked_file_download(url: str, headers={}, dest_file: str = None, timeout=10):

    redirect_count = 0
    current_url = url

    while redirect_count < 10:
        
        # parse host and make request
        host, port, path, conn_class = parse_url(current_url)
        conn = conn_class(host, port, timeout=timeout)

        conn.request('GET', path, headers=headers)

        response = conn.getresponse()

        # handle redirects
        if response.status in (301, 302, 303, 307, 308):
            location = response.getheader('Location')
            if not location:
                break
            current_url = location
            conn.close()
            redirect_count += 1
            continue
        else:
            # process response
            file_path = response.getheader('file_path', '')
            if dest_file == None: dest_file = file_path
            file_size = int(response.getheader('file_size', ''))
            i_recieved = 0
            with open(CLIENT_DIR + '/' + dest_file, 'wb') as f:
                while True:
                    # Read the chunk size line
                    chunk_size_line = response.fp.readline().strip()
                    if not chunk_size_line:
                        break
                    try:
                        size = int(chunk_size_line, 16)
                    except ValueError:
                        # Invalid chunk size
                        break
                    if size == 0:
                        # Last chunk
                        break
                    # Read the chunk data
                    chunk_data = response.fp.read(size)
                    # Read the trailing CRLF
                    response.fp.read(2)
                    # Write chunk to file
                    f.write(chunk_data)

                    i_recieved += size
                    print(START_OF_LINE_AND_CLEAR + file_path + ' --> ' + str(100 * i_recieved / file_size) + '%', end='')
            print(START_OF_LINE_AND_CLEAR, end='')

            return response.status, file_path
        
    # Too many redirects
    raise Exception("Too many redirects")

def display_diff(file_str: str, old_file_str: str):
    lines = file_str.strip().split('\n')
    old_lines = old_file_str.strip().split('\n')

    # make reference dict for efficiency
    old_lines_dict = {}
    for i, line in enumerate(old_lines):
        if line in old_lines_dict:
            old_lines_dict[line].append(i)
        else:
            old_lines_dict[line] = [i]


    # find common lines
    lines_in_common = []
    for i, line in enumerate(lines):
        if line in old_lines_dict:
            lines_in_common.append(line)


    # print out lines with colors
    l = 0
    lc = 0
    ol = 0
    while ol < len(old_lines) or l < len(lines) or lc < len(lines_in_common):
        
        common_line = None if lc >= len(lines_in_common) else lines_in_common[lc]

        if ol < len(old_lines):
            old_line = old_lines[ol]
            while old_line != common_line and ol < len(old_lines):
                print(RED, old_line, ANSII_RESET, sep='')
                ol += 1
                old_line = None if ol >= len(old_lines) else old_lines[ol]

        if l < len(lines):
            line = lines[l]
            while line != common_line and l < len(lines):
                print(GREEN, line, ANSII_RESET, sep='')
                l += 1
                line = None if l >= len(lines) else lines[l]

        if lc < len(lines_in_common):
            print(common_line)
        lc += 1
        l += 1
        ol += 1

def print_rainbow(str: str, end='\n'):
    colors = [RED, ORANGE, YELLOW, GREEN, BLUE, INDIGO, VIOLET]
    for i, c in enumerate(str):
        color = colors[i % len(colors)]
        print(color, c, sep='', end='')
    print(ANSII_RESET, end=end)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't need to be reachable
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    return local_ip

def get_network_ip():
    local_ip = get_local_ip()
    i = len(local_ip) - 1
    while i >= 0 and local_ip[i] != '.':
        i -= 1
    
    return local_ip[:i] + ".0/24"




# CLIENT METHODS

CLIENT_DIR = 'client_files'
        
def CLIENT_PING(host):

    try:
        status, response = get(host + '/ping', timeout=1, headers={'password' : PASSWORD})
        return status == 200 and response == 'up'
    except Exception as e:
        return False
        
def CLIENT_SYNC():
    print()
    files = get_all_files_relative(CLIENT_DIR)
    file_path_to_file_hash = {}
    for file in files:
        file_hash = hash(CLIENT_DIR + "/" + file)
        file_path_to_file_hash[file] = {
            'hash': file_hash,
            'date': get_file_last_modified(CLIENT_DIR + "/" + file).strftime(DATE_FORMAT)
        }


    status, response = post(URL + '/sync', file_path_to_file_hash, headers={'password' : PASSWORD})

    if status == 409:
        file_path_to_file_contents = response['file_path_to_file_contents']
        for file_path, file_contents in file_path_to_file_contents.items():

            is_large = file_contents == FILE_TOO_LARGE or os.path.getsize(CLIENT_DIR+ "/" + file_path) > SIZE_LIMIT
            if not is_large:
                decoded_contents = base64.b64decode(file_contents).decode('utf-8', errors='ignore')
                local_contents = base64.b64decode(read(CLIENT_DIR+ "/" + file_path)).decode('utf-8', errors='ignore')
                print()
                print(BLUE + '```' + file_path + ANSII_RESET)
                display_diff(local_contents, decoded_contents)
                print(BLUE + '```' + file_path + ANSII_RESET)
                print()
            else:
                print()
                print(BLUE + file_path + ANSII_RESET + ' (too large to display)')
                print()
                

            print("*********************")
            print_rainbow('CHANGE ' + TABLE_FLIP)
            print("*********************")
            print()
            print('You have a new file or a newer version of a file.')
            print()
            print_rainbow('Server Files Behind Yours:')
            for file, file_contents in file_path_to_file_contents.items():
                print(file)
            print()

            print('''
Above is a diff of the first file with the server's version of the file. You can do the following:
- '' -> (upload your version for all the files above)
- 'up' -> (upload your version to the server for the first file. * you can also make changes before doing this)
- 'pull' -> (replaces the first file with the server's version)
- 'pull' <new_path> -> (copies the server's file to a new file)
- <anything else> -> (cancel the sync)
            ''')

            cmd = input()
            print_rainbow(PUT_TABLE_BACK)
            print()
            if cmd == '':

                print("--", end='')
                print_rainbow('Uploaded', end='')
                print("--")

                for file_path, file_contents in file_path_to_file_contents.items():
                    up_status, response = chunked_file_upload(
                        URL + '/upload', 
                        CLIENT_DIR + "/" + file_path, 
                        'POST',
                        headers={'password' : PASSWORD, 'file_path' : file_path}
                    )
                    print(file_path)
                break

            elif cmd == 'up':
                up_status, response = chunked_file_upload(
                    URL + '/upload', 
                    CLIENT_DIR + "/" + file_path, 
                    'POST',
                    headers={'password' : PASSWORD, 'file_path' : file_path}
                )
                print("--", end='')
                print_rainbow('Uploaded', end='')
                print("--")
                print(file_path)
                print()
            elif cmd.startswith('pull'):
                splits = cmd.split(' ')
                if len(splits) > 1:
                    dest_file = splits[1]
                    chunked_file_download(URL + '/download', dest_file=dest_file, headers={'password' : PASSWORD, 'file_path' : file_path})
                    print()
                    print_rainbow('Copied to -> ', end='')
                    print(dest_file)
                    print()
                    return
                
                else:
                    chunked_file_download(URL + '/download', headers={'password' : PASSWORD, 'file_path' : file_path})
                
            else:
                print("*********")
                print_rainbow('CANCELLED')
                print("*********")
                return


    if status != 409:
        file_path_to_file_contents = response
        print("--", end='')
        print_rainbow('Server Updates', end='')
        print("--")
        for file_path, contents in file_path_to_file_contents.items():
            if contents == FILE_TOO_LARGE:
                chunked_file_download(URL + '/download', headers={'password' : PASSWORD, 'file_path' : file_path})
            else:
                binary_data = base64.b64decode(contents)
                write_file_with_dirs(CLIENT_DIR + "/" + file_path, binary_data)

            if file_path in file_path_to_file_hash:
                print(BLUE + file_path + ANSII_RESET)
            else:
                print(GREEN + file_path + ANSII_RESET)

    print()
    print("*************")
    print_rainbow('SYNCED ' + WAVING)
    print("*************")
    return file_path_to_file_contents

def CLIENT_LIST_FILES():
    status, response = get(URL + '/list_files', timeout=1000, headers={'password' : PASSWORD})
    print()
    print_dir_structure(response)



# ENDPOINTS

def SYNC(file_path_to_file_hash: Dict[str, Dict[str, str]]):
    # print('made it')
    files = get_all_files_relative(DIRECTORY)


    # check if user has sent any new files
    server_files = set(files)
    new_user_files = {}
    for file_path, file_hash_and_date in file_path_to_file_hash.items():
        if file_path not in server_files:
            new_user_files[file_path] = ''
        else:
            file_hash = hash(DIRECTORY + "/" + file_path)
            client_modified_date = datetime.strptime(
                file_path_to_file_hash[file_path]['date'], 
                DATE_FORMAT
            )
            modified_date = get_file_last_modified(DIRECTORY + "/" + file_path)

            if file_hash != file_path_to_file_hash[file_path]['hash']:
                if client_modified_date > modified_date:
                    file_contents = None
                    if os.path.getsize(DIRECTORY + "/" + file_path) > SIZE_LIMIT:
                        file_contents = FILE_TOO_LARGE
                    else:
                        file_contents = read(DIRECTORY + "/" + file_path)
                    new_user_files[file_path] = file_contents


    if len(new_user_files) > 0:
        content = {
            "error": "You have a newer file version", 
            "file_path_to_file_contents": new_user_files
        }
        return 409, content
    
    

    # get any files on the server that are out of date on the client
    file_path_to_file = {}
    for file_path in files:
        file_contents = None
        if os.path.getsize(DIRECTORY + "/" + file_path) > SIZE_LIMIT:
            file_contents = FILE_TOO_LARGE
        else:
            file_contents = read(DIRECTORY + "/" + file_path)

        if file_path in file_path_to_file_hash:
            file_hash = hash(DIRECTORY + "/" + file_path)
            
            
            client_modified_date = datetime.strptime(
                file_path_to_file_hash[file_path]['date'], 
                DATE_FORMAT
            )
            modified_date = get_file_last_modified(DIRECTORY + "/" + file_path)

            if file_hash != file_path_to_file_hash[file_path]['hash']:
                file_path_to_file[file_path] = file_contents
        else:
            file_path_to_file[file_path] = file_contents


    return 200, file_path_to_file

def PING():
    return 200, 'up'

def LIST_FILES():
    files = get_all_files_relative(DIRECTORY)

    return 200, files


class Server(BaseHTTPRequestHandler):

    def password_check(self):
        headers = self.headers
        password = headers['password']

        if password != PASSWORD:
            raise Exception('bad password')

    def DOWNLOAD(self, file_path):
        try:
            file_size = os.path.getsize(DIRECTORY + "/" + file_path)

            # Check if file exists
            with open(DIRECTORY + '/' + file_path, 'rb') as f:
                self.send_response(200)
                # Send headers
                self.send_header('Transfer-Encoding', 'chunked')
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('file_path', file_path)
                self.send_header('file_size', file_size)
                self.end_headers()

                # Read and send file in chunks
                while True:
                    chunk = f.read(1024*1024)  # 1MB chunks
                    if not chunk:
                        break
                    # Send chunk size in hex + CRLF
                    self.wfile.write(f"{len(chunk):X}\r\n".encode('utf-8'))
                    # Send chunk data
                    self.wfile.write(chunk)
                    # Send CRLF after chunk
                    self.wfile.write(b"\r\n")

                # Send zero-length chunk to indicate end
                self.wfile.write(b"0\r\n\r\n")
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")


    def do_GET(self):
        json_str = None
        status = 200
        try:
            self.password_check()

            response_body = None

            if self.path == '/ping':
                status, response_body = PING()
            elif self.path == '/download':
                file_path = self.headers.get('file_path')
                self.DOWNLOAD(file_path)
                return
            elif self.path == '/list_files':
                status, response_body = LIST_FILES()
                
            json_str = json.dumps(response_body)

        except Exception as e:
            response_obj = {
                "error": str(e)
            }
            json_str = json.dumps(response_obj)

        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json_str.encode('utf-8'))

    def do_POST(self):
        json_str = None
        status = 200
        try:
            self.password_check()


            transfer_encoding = self.headers.get('Transfer-Encoding', '').lower()
            body = None
            if 'chunked' in transfer_encoding:
                if self.path == '/upload':
                    self.handle_chunked()
                return
            else:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                req_json = post_data.decode('utf-8')
                body = json.loads(req_json)

            response_body = None

            if self.path == '/sync':
                status, response_body = SYNC(body)

            json_str = json.dumps(response_body)

        except Exception as e:
            response_obj = {
                "error": str(e)
            }
            json_str = json.dumps(response_obj)

        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json_str.encode('utf-8'))
        
    
    def handle_chunked(self):
        file_path = DIRECTORY + '/' + self.headers.get('file_path')
        # Open a file to write the incoming data
        with open(file_path, 'wb') as f:
            while True:
                # Read the chunk size line
                chunk_size_line = self.rfile.readline().strip()
                if not chunk_size_line:
                    break
                # Convert hex size to int
                try:
                    chunk_size = int(chunk_size_line, 16)
                except ValueError:
                    # Send appropriate response, or return error
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid chunk size")
                    return
                if chunk_size == 0:
                    # End of chunks
                    break
                # Read the chunk data
                chunk_data = self.rfile.read(chunk_size)
                # Read the trailing CRLF after chunk data
                self.rfile.read(2)
                # Write chunk directly to file
                f.write(chunk_data)

        # After completing, send response
        self.send_response(200)
        self.end_headers()
        message = "File uploaded successfully."
        self.wfile.write(json.dumps(message).encode('utf-8'))



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A file server for syncing folders across devices")
    
    parser.add_argument('--server', action='store_true', help='Start the server on this machine. If ommited you\'re running as a client.')
    parser.add_argument('--dir', type=str, required=True, help='directory to be synced with server (or clients if running as server)')
    parser.add_argument('--url', type=str, help='Server url if running as client. Otherwise the local network is scanned for a server')
    parser.add_argument('--password', type=str, help='Password used either as server or client. Otherwise no password is used.')
    parser.add_argument('--la', action='store_true', help='Whether to just list the files on the server instead of syncing')
    args = parser.parse_args()


    if args.password:
        PASSWORD = args.password

    if args.server:
        # ifconfig

        DIRECTORY = args.dir

        server_address = ('', PORT)
        httpd = HTTPServer(server_address, Server)

        print("Serving on port " + str(PORT) + " ...")
        httpd.serve_forever()
    else:


        # scan for the server on local network if no url
        URL = args.url
        CLIENT_DIR = args.dir
        if not URL:
            
            def check_ip(ip):
                url = f"{ip}:{PORT}"
                if CLIENT_PING(url):
                    return url
                else:
                    return None
                
            # subnet = ipaddress.IPv4Network('192.168.1.0/24')
            network = get_network_ip()
            print(RED + "Searching for server on local network " + network + " ..." + ANSII_RESET)
            print()
            subnet = ipaddress.IPv4Network(network, strict=False)
            with ThreadPoolExecutor(max_workers=255) as executor:
                # Submit all IPs to the executor
                futures = [executor.submit(check_ip, str(ip)) for ip in subnet.hosts()]

                for future in concurrent.futures.as_completed(futures):
                    try:
                        if future.result():
                            URL = future.result()
                            
                            # Cancel all other pending futures
                            for f in futures:
                                if not f.done():
                                    f.cancel()

                            print(BLUE + NICE + ANSII_RESET + ' ', end='')
                            print_rainbow(URL, end='')
                            print(BLUE + ' ' + NICE_OTHER + ANSII_RESET)

                            if args.la:
                                CLIENT_LIST_FILES()
                            else:
                                CLIENT_SYNC()

                    except Exception as e:
                        pass
                
                done, not_done = concurrent.futures.wait(futures)
                if not URL:
                    print_rainbow(SHRUG)
                    print("no server found")
                    print()


        else:
            if args.la:
                CLIENT_LIST_FILES()
            else:
                CLIENT_SYNC()









