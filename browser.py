import socket
import ssl
import gzip

from utils import unchunk, Cache

DEFAULT_ENCODING = 'utf-8'

MAX_REDIRECT = 5

AMP_CHAR_CODES = {
    "quot": '"',
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "nbsp": " ",
    "ndash": "-",
    "copy": "©",
}

redirect_counter = 0

cache = Cache()

def request(url, additional_headers = {}, redirect_number = 0):
    full_url = url
    scheme, url = url.split(":", 1)

    assert redirect_number < MAX_REDIRECT

    assert scheme in ["http", "https", "file", "data"], \
        f"Unknown scheme {scheme}"

    if scheme not in ["data"]:
        # all schemes except data are followed by "//" 
        host, *path = url[2:].split('/', 1)

        # if path is provided, add it, otherwise default to "/"
        path = "/" + path[0] if path else "/index.html"

    if scheme in ["http", "https"]:
        if cache.has_valid_cache(full_url):
            response_headers, body = cache.retrieve(full_url)
        else:
            s = socket.socket(
                family=socket.AF_INET,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )

            port = 80 if scheme == "http" else 443

            if ":" in host:
                # if port is provided, overwrite
                host, port = host.split(":", 1)
                port = int(port)

            if scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=host)

            s.connect((host, port))

            http_request = (
                    b"GET " + bytes(path, 'utf-8') + b" HTTP/1.1\r\n" + 
                    b"Host: " + bytes(host, 'utf-8') + b"\r\n" + 
                    b"Connection: close\r\n" +
                    b"User-Agent: Manyk\r\n" +
                    b"Accept-Encoding: gzip\r\n"
                    )

            for key, value in additional_headers:
                # Add all additional headers to request
                http_request += bytes(f"{key}: {value}\r\n")
            
            http_request += b"\r\n" # Add proper HTTP file ending
        

        
            s.send(http_request)

            response = s.makefile("rb", newline="\r\n")

            statusline = response.readline().decode()
            version, status, explanation = statusline.split(' ', 2) # No more than 2 to allow explanation to be a sentence

            response_headers = {}
            while True:
                line = response.readline().decode()
                if line == "\r\n": break
                header, value = line.split(':', 1)
                response_headers[header.lower()] = value.strip()

            if 299 < int(status) < 399:
                # redirect
                new_url = f"{scheme}:{host}{response_headers['location']}" if response_headers['location'].startswith('/') else response_headers['location']
                return request(new_url, additional_headers, redirect_number + 1)

            else:
                encoding = DEFAULT_ENCODING
                if "charset" in response_headers.get("content-type"):
                    mime, charset = response_headers["content-type"].split(';')
                    encoding = charset.split('=')[1].strip().lower()

                if "chunked" in response_headers.get('transfer-encoding', {}):
                    body = unchunk(response)
                else:
                    body = response.read()

                if 'content-encoding' in response_headers:
                    assert "gzip" in response_headers.get('content-encoding')
                    body = gzip.decompress(body).decode(encoding=encoding)
                else: 
                    body = body.decode(encoding=encoding)

                s.close()
            cache.store(full_url, response_headers, body)

    elif scheme == "file":
        with open(path, "r") as file:
            file = open(path, "r")
            body = file.read()
            response_headers = ""
    
    elif scheme == "data":
        typeinfo, data = url.split(',', 1)

        # Ignoring media-type, charset and base64 for now
        if not typeinfo:
            mediatype, *mediaoptions = ["text/plain", "charset=US-ASCII"]
        else:
            mediatype, *mediaoptions = typeinfo.split(";")

        response_headers = ""
        body = "<body>" + data + "\r\n" + "</body>"

    return response_headers, body

def show(body):
    in_angle = False
    in_body_tag = False
    possible_amp_code_index = 0
    current_tag = ""
    text = ""
    for c in body:
        if c == "<":
            in_angle = True
        elif c == ">":
            in_angle = False
            if current_tag == "body" or current_tag.startswith('body '):
                in_body_tag = True
            elif current_tag == "/body":
                in_body_tag = False
            current_tag = ""
        elif in_angle:
            current_tag += c
        elif c == ";":
            possible_amp_code = text[possible_amp_code_index + 1:]
            if possible_amp_code in AMP_CHAR_CODES:
                # ensure we only replace last portion
                text = text[:possible_amp_code_index] + AMP_CHAR_CODES[possible_amp_code]
            elif in_body_tag:
                text += c
        elif not in_angle and in_body_tag:
            if c == "&":
                possible_amp_code_index = len(text) 
            text += c

    print(text)

def to_source(body):
    return "<body>" + body.replace("<", "&lt;").replace(">", "&gt;") + "</body>" 

def load(url):
    if url.startswith('view-source:'):
        _, url = url.split(":", 1)
        headers, body = request(url)
        body = to_source(body)
    else:
        headers, body = request(url)
    show(body)

if __name__ == "__main__":
    import sys
    load(sys.argv[1])

