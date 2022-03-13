import pathlib
from datetime import datetime, timedelta
from hashlib import blake2b
import json

def unchunk(chunked_data):
    data = b""
    while True:
        line = chunked_data.readline()
        if line == b"0\r\n": break
        chunk_length = int(line[:-2], 16) + 2
        chunk = chunked_data.read(chunk_length)[:-2]
        data += chunk
    return data

class Cache:
    def __init__(self):
        self.local_cache = pathlib.Path('./.cache')
        
        if not self.local_cache.is_dir():
            self.local_cache.mkdir()

    def has_valid_cache(self, url):
        hash_algo = blake2b(digest_size=20)
        hash_algo.update(bytes(url, encoding='utf8'))
        url_hash = hash_algo.hexdigest()
        cache_file = self.local_cache / url_hash

        if cache_file.is_file():
            with cache_file.open() as cache:
                expiry_date = cache.readline().strip()
                if datetime.utcnow() < datetime.fromisoformat(expiry_date):
                    return True
            cache_file.unlink()

        return False


    def store(self, url, headers, body):
        hash_algo = blake2b(digest_size=20)
        cache_control_header = headers.get('cache-control', False)

        if cache_control_header and 'max-age' in cache_control_header:
            age = headers.get('age', 0)
            _, max_age = cache_control_header.split('=', 1) # Input string 'max-age=<age>'

            cache_time_left = int(max_age) - int(age)

            caching_expiry = datetime.utcnow() + timedelta(seconds=cache_time_left)

            hash_algo.update(bytes(url, encoding='utf8'))

            url_hash = hash_algo.hexdigest()
            
            self.local_cache.touch(url_hash)

            cache_file = self.local_cache / url_hash

            cache_content = bytes(
                str(caching_expiry) + "\r\n" +
                json.dumps(headers) + "\r\n" +
                body + "\r\n",
                encoding = 'utf8'
            )

            cache_file.write_bytes(cache_content)

    def retrieve(self, url):
        hash_algo = blake2b(digest_size=20)
        hash_algo.update(bytes(url, encoding='utf8'))
        url_hash = hash_algo.hexdigest()
        cache_file = self.local_cache / url_hash


        if cache_file.is_file():
            with cache_file.open() as cache:
                expiry_date = cache.readline() # Ignoring this line
                headers = cache.readline().strip()
                decoded_headers = json.loads(headers)
                body = cache.read()
                return decoded_headers, body

