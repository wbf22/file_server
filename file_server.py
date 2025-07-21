import base64
from datetime import datetime
import hashlib
import http
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from typing import Dict, List
from urllib.parse import urlparse



DIRECTORY = 'files'
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
URL = "http://localhost:8000/"

RED = '\x1b[38;2;255;0;0m'
ORANGE = '\x1b[38;2;230;76;0m'
YELLOW = '\x1b[38;2;230;226;0m'
GREEN = '\x1b[38;2;0;186;40m'
BLUE = '\x1b[38;2;0;72;255m'
INDIGO = '\x1b[38;2;84;0;230m'
VIOLET = '\x1b[38;2;176;0;230m'
ANSII_RESET = '\x1b[0m'


# UTIL FUNCTION
def get_all_files_relative(directory: str) -> List[str]:
    files_list = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Create absolute or relative path as needed
            full_path = os.path.join(root, file)
            relative_path = os.path.relpath(full_path, directory)
            files_list.append(relative_path)
    return files_list

def hash(content: str, algorithm: str = 'sha256') -> str:
    hash_func = hashlib.new(algorithm)
    # Encode the string to bytes
    content_bytes = content.encode('utf-8')
    hash_func.update(content_bytes)
    return hash_func.hexdigest()

def read(file_path: str) -> str:
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
    parsed_url = urlparse(url)
    scheme = parsed_url.scheme
    host = parsed_url.hostname
    port = parsed_url.port
    path = parsed_url.path
    if parsed_url.query:
        path += '?' + parsed_url.query
    conn_class = http.client.HTTPSConnection if scheme == 'https' else http.client.HTTPConnection
    if port is None:
        port = 443 if scheme == 'https' else 80

    return host, port, path, conn_class

def post(url: str, body: any, headers={'Content-type': 'application/json'}) -> list[int, any]:

    if headers is None:
        headers = {'Content-Type': 'application/json'}

    redirect_count = 0
    current_url = url

    while redirect_count < 10:
        
        # parse host and make request
        host, port, path, conn_class = parse_url(current_url)
        conn = conn_class(host, port)
        payload = json.dumps(body)
        conn.request("POST", path, body=payload, headers=headers)
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

def print_rainbow(str: str):
    colors = [RED, ORANGE, YELLOW, GREEN, BLUE, INDIGO, VIOLET]
    for i, c in enumerate(str):
        color = colors[i % len(colors)]
        print(color, c, sep='', end='')
    print(ANSII_RESET)



# CLIENT METHODS



CLIENT_DIR = 'client_files'

def CLIENT_SYNC():
    files = get_all_files_relative(CLIENT_DIR)
    file_path_to_file_hash = {}
    for file in files:
        content = read(CLIENT_DIR + "/" + file)
        file_hash = hash(content)
        file_path_to_file_hash[file] = {
            'hash': file_hash,
            'date': get_file_last_modified(CLIENT_DIR + "/" + file).strftime(DATE_FORMAT)
        }



    status, response = post(URL + 'sync', file_path_to_file_hash)

    while status == 409:
        file_path_to_file_contents = response['file_path_to_file_contents']
        file_to_send = ''
        for file_path, file_contents in file_path_to_file_contents.items():
            print()
            print('```' + file_path)
            decoded_contents = base64.b64decode(file_contents).decode('utf-8', errors='ignore')
            local_contents = base64.b64decode(read(CLIENT_DIR+ "/" + file_path)).decode('utf-8', errors='ignore')
            display_diff(local_contents, decoded_contents)
            print('```')
            print()
            file_to_send = file_path

        print("******")
        print_rainbow('CHANGE')
        print("******")
        print('''
You have a new file or a newer version of a file.
    
Above is a diff of your file with the server's version of the file. Make changes in your file 
(if needed) and then hit enter to upload your file to the server. Type anything else and hit enter
to cancel
        ''')

        cmd = input()
        if cmd == '':
            contents = read(CLIENT_DIR + "/" + file_to_send)
            status, response = post(URL + 'upload', [file_to_send, contents])

            contents = read(CLIENT_DIR + "/" + file_to_send)
            file_hash = hash(contents)
            file_path_to_file_hash[file_to_send] = {
                'hash': file_hash,
                'date': get_file_last_modified(CLIENT_DIR + "/" + file_to_send).strftime(DATE_FORMAT)
            }

        else:
            print(BLUE + 'CANCELLED' + ANSII_RESET)
            return

        status, response = post(URL + 'sync', file_path_to_file_hash)

    file_path_to_file_contents = response
    for file_path, contents in file_path_to_file_contents.items():
        binary_data = base64.b64decode(contents)
        write_file_with_dirs(CLIENT_DIR + "/" + file_path, binary_data)


    return file_path_to_file_contents
        
        







# ENDPOINTS

def UPLOAD(file_path_and_contents: list[str]):
    file_path, contents = file_path_and_contents
    binary_data = base64.b64decode(contents)
    write_file_with_dirs(DIRECTORY + "/" + file_path, binary_data)
    
    return 204, ''


def SYNC(file_path_to_file_hash: Dict[str, Dict[str, str]]):
    # print('made it')
    files = get_all_files_relative(DIRECTORY)
    server_files = set(files)

    # get any files on the server that are out of date on the client
    file_path_to_file = {}
    for file in files:
        file_path = DIRECTORY + "/" + file
        file_contents = read(file_path)
        if file in file_path_to_file_hash:
            file_hash = hash(file_contents)
            client_modified_date = datetime.strptime(
                file_path_to_file_hash[file]['date'], 
                DATE_FORMAT
            )
            modified_date = get_file_last_modified(file_path)

            if file_hash != file_path_to_file_hash[file]['hash']:
                if client_modified_date > modified_date:
                    content = {
                        "error": "You have a newer file version", 
                        "file_path_to_file_contents": {
                            file: file_contents 
                        }
                    }
                    return 409, content
                else:
                    file_path_to_file[file] = file_contents


        else:
            file_path_to_file[file] = file_contents

    # check if user has sent any new files
    for file_path, file_hash_and_date in file_path_to_file_hash.items():
        if file_path not in server_files:
            content = {
                "error": "You have a newer file version", 
                "file_path_to_file_contents": {
                    file_path: '' 
                }
            }
            return 409, content

    return 200, file_path_to_file


class Server(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<html><body><h1>Hello, World!</h1></body></html>")



    def do_POST(self):
        json_str = None
        status = 200
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            req_json = post_data.decode('utf-8')
            body = json.loads(req_json)
            response_body = None

            if self.path == '/sync':
                status, response_body = SYNC(body)
            elif self.path == '/upload':
                status, response_body = UPLOAD(body)

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
        


if __name__ == "__main__":
    server_address = ('', 8000)
    httpd = HTTPServer(server_address, Server)

    print("Serving on port 8000...")
    httpd.serve_forever()







