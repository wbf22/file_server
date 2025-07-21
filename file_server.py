from datetime import datetime
import hashlib
import json
import os
from typing import Dict, List, Optional
from fastapi import FastAPI, File, Response, UploadFile, Query
from fastapi.responses import JSONResponse
import requests

app = FastAPI()


DIRECTORY = 'files'
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
URL = "http://localhost:8000/"

RED = '\x1b[38;2;255;0;0m'
BLUE = '\x1b[38;2;0;72;255m'
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
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()
    
def get_file_last_modified(file_path: str) -> datetime:
    # Get the timestamp of last modification
    timestamp = os.path.getmtime(file_path)
    # Convert timestamp to a datetime object
    return datetime.fromtimestamp(timestamp)


def write_file_with_dirs(file_path, content, open_arg='wb'):
    # Ensure parent directories exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    # Write content to the file
    with open(file_path, open_arg) as file:
        file.write(content)





# CLIENT METHODS



CLIENT_DIR = 'client_files'

def CLIENT_REFRESH():
    files = get_all_files_relative(CLIENT_DIR)
    file_path_to_file_hash = {}
    for file in files:
        content = read(CLIENT_DIR + "/" + file)
        file_hash = hash(content)
        file_path_to_file_hash[file] = {
            'hash': file_hash,
            'date': get_file_last_modified(CLIENT_DIR + "/" + file).strftime(DATE_FORMAT)
        }



    response = requests.post(URL + 'refresh/', json=file_path_to_file_hash)

    while response.status_code == 409:
        data = response.json()
        file_path_to_file_contents = data['file_path_to_file_contents']
        file_to_send = ''
        for file_path, file_contents in file_path_to_file_contents.items():
            print()
            print('```' + file_path)
            print('```')
            print()
            print(file_contents)
            print()
            file_to_send = file_path

        print(RED + 'FILE CONFLICT' + ANSII_RESET)
        print()
        print('''
You have a new file or a newer version of a file.
    
Above is the server's version of your file if it exists. Make changes in your file 
(if needed) and then type 'send' to upload your file to the server. Type anything else to cancel
        ''')

        cmd = input()
        if cmd == 'send':
            files = {'file': open(CLIENT_DIR + "/" + file_to_send, 'rb')}
            params = {'file_path': file_to_send}
            response = requests.post(URL + 'upload/', params=params, files=files)

            contents = read(CLIENT_DIR + "/" + file_to_send)
            file_hash = hash(contents)
            file_path_to_file_hash[file_to_send] = {
                'hash': file_hash,
                'date': get_file_last_modified(CLIENT_DIR + "/" + file_to_send).strftime(DATE_FORMAT)
            }

        else:
            print(BLUE + 'CANCELLED' + ANSII_RESET)
            return

        response = requests.post(URL + 'refresh/', json=file_path_to_file_hash)

    file_path_to_file_contents = json.loads(response.json())
    for file_path, contents in file_path_to_file_contents.items():
        write_file_with_dirs(CLIENT_DIR + "/" + file_path, contents, 'w')
        
        



def CLIENT_PUSH():

    CLIENT_REFRESH()


    








# ENDPOINTS


@app.post("/upload")
async def upload_file(file_path: str, file: UploadFile = File(...)):
    # Read the file content (optional)
    contents = await file.read()
    write_file_with_dirs(DIRECTORY + "/" + file_path, contents)
    
    return Response(status_code=204)


@app.post("/refresh/")
async def refresh(file_path_to_file_hash: Dict[str, Dict[str, str]]):
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
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": "You have a newer file version", 
                            "file_path_to_file_contents": {
                                file: file_contents 
                            }
                        }
                    ) 
                else:
                    file_path_to_file[file] = file_contents


        else:
            file_path_to_file[file] = file_contents

    # check if user has sent any new files
    for file_path, file_hash_and_date in file_path_to_file_hash.items():
        if file_path not in server_files:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "You have a newer file version", 
                    "file_path_to_file_contents": {
                        file_path: '' 
                    }
                }
            ) 

    return json.dumps(file_path_to_file)







