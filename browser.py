import socket
import ssl
import gzip
import tkinter
import tkinter.font

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
    "#39": "'",
}

WIDTH, HEIGHT = 800, 600
HSTEP, VSTEP = 13, 18

DEFAULT_LEADING = 1.25 # proportional to ascent

BROWSER_MODES = {
    "source": "source",
    "normal": "normal"
}

FONTS = {}

FONT_MODIFIERS = {
    "subscript": "subscript",
    "superscript": "superscript",
}

redirect_counter = 0

cache = Cache()

def get_font(size, weight, slant, family):
    key = (size, weight, slant, family)

    if key not in FONTS:
        font = tkinter.font.Font(
            family=family,
            size=size,
            weight=weight,
            slant=slant,
        )
        FONTS[key] = font
    return FONTS[key]

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
        body = data

    return response_headers, body

class Text:
    def __init__(self, text, parent):
        self.text = self.transform_amp(text)
        self.children = []
        self.parent = parent

    def __repr__(self):
        return repr(self.text)

    def visualize(self, indent=0):
        print(" " * indent, self.text)

    def transform_amp(self, input_text):
        text = ""
        possible_amp_code_index = 0
        for c in input_text:
            if c == ";":
                possible_amp_code = text[possible_amp_code_index + 1:]
                if possible_amp_code in AMP_CHAR_CODES:
                    # ensure we only replace last portion
                    text = text[:possible_amp_code_index] + AMP_CHAR_CODES[possible_amp_code]
                else:
                    text += c
            else:
                if c == "&":
                    possible_amp_code_index = len(text)
                text += c
        
        return text

class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.children = []
        self.parent = parent
        self.attributes = attributes
    
    def __repr__(self):
        return "<" + self.tag + ">"
    
    def visualize(self, indent=0):
        if self.tag in HTMLParser.SELF_CLOSING_TAGS:
            print(" " * indent, "<" + self.tag + " />")
        else:
            print(" " * indent, "<" + self.tag + ">")
        for child in self.children:
            child.visualize(indent + 2)
        
        if self.tag not in HTMLParser.SELF_CLOSING_TAGS:
            print(" " * indent, "</" + self.tag + ">")

class HTMLParser:
    SELF_CLOSING_TAGS = [
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    ]

    HEAD_TAGS = ["base", "basefont", "bgsound", "noscript", "link", "meta", "title", "style", "script"]

    def __init__(self, body):
        self.body = body
        self.unfinished = []

    def get_attributes(self, text):
        parts = text.split(" ", 1)
        tag = parts[0].lower()
        attributes = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
                attributes[key.lower()] = value
            else:
                attributes[attrpair.lower()] = ""
            
        return tag, attributes

    def add_text(self, text):
        if text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)
    
    def add_tag(self, tag):
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"): return

        self.implicit_tags(tag)

        if tag == "p" and repr(self.unfinished[-1]) == "<p>":
            # If '<p>' child of '<p>'
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)

        if tag.startswith("/"):
            if len(self.unfinished) == 1: return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in HTMLParser.SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def implicit_tags(self, tag):
        while True:
            open_tags = [node.tag for node in self.unfinished]

            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            else:
                break

    def parse(self):
        text = ""
        in_tag = False
        in_comment = False
        in_script = False
        current_pattern = ""
        for c in self.body:
            if in_tag and "!--".startswith(current_pattern + c) and not in_comment:
                if current_pattern == "!--":
                    text = ""
                    in_tag = False
                    in_comment = True
                current_pattern += c
            elif current_pattern:
                current_pattern = ""

            if not in_comment and not current_pattern:
                if c == "<":
                    in_tag = True
                    if text and not in_script: self.add_text(text)
                    text = ""
                elif c == ">":                    
                    in_tag = False
                    if text.startswith("script"):
                        in_script = True
                    elif text.startswith("/script"):
                        in_script = False
                    self.add_tag(text)
                    text = ""
                else:
                    text += c
            elif in_comment:
                text += c
                if "-->" in text:
                    text = ""
                    in_comment = False
            else:
                text += c

        return self.finish()

    def finish(self):
        if len(self.unfinished) == 0:
            self.add_tag("html")
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()

class Layout:
    def __init__(self, tree, font, canvas_width):
        self.display_list = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.canvas_width = canvas_width
        self.line = []
        
        self.original_font_family = font.actual('family')
        self.original_font_size = font.actual('size')

        self.current_modifier = None

        self.font_weight = font.actual('weight')
        self.font_slant = font.actual('slant')
        self.font_size = font.actual('size')
        self.font_family = font.actual('family')

        self.recurse(tree)
        self.flush()

    def open_tag(self, tag):
        if tag == "i" or tag == "em":
            self.font_slant = "italic"
        elif tag == "b"  or tag == "strong":
            self.font_weight = "bold"
        elif tag == "small":
            self.font_size -= 2
        elif tag == "big":
            self.font_size += 4
        elif tag == "br":
            self.flush()
        elif tag == "code":
            self.font_family = "Monaco"
            self.font_size -= 2
        elif tag == "h1":
            self.font_size = 36
        elif tag == "h2":
            self.font_size = 24
        elif tag == "h3":
            self.font_size = 18
        elif tag == "sup":
            self.current_modifier = FONT_MODIFIERS["superscript"]
        elif tag == "sub":
            self.current_modifier = FONT_MODIFIERS["subscript"]

    def close_tag(self, tag):
        if tag == "i" or tag == "em":
            self.font_slant = "roman"
        elif tag == "b" or tag == "strong":
            self.font_weight = "normal"
        elif tag == "small":
            self.font_size += 2
        elif tag == "big":
            self.font_size -= 4
        elif tag == "p":
            self.flush()
            self.cursor_y += VSTEP
        elif tag == "code":
            self.font_family = self.original_font_family
            self.font_size += 2
        elif tag == "pre":
            self.flush()
            self.cursor_y += VSTEP
        elif tag == "h1":
            self.font_size = self.original_font_size
            self.flush()
            self.cursor_y += VSTEP
        elif tag == "h2":
            self.font_size = self.original_font_size
            self.flush()
            self.cursor_y += VSTEP
        elif tag == "h3":
            self.font_size = self.original_font_size
            self.flush()
        elif tag == "sup":
            self.current_modifier = None
        elif tag == "sub":
            self.current_modifier = None

    def recurse(self, tree):
        if isinstance(tree, Text):
            self.text(tree)
        else:
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)

    def text(self, token):
        font = get_font(self.font_size, self.font_weight, self.font_slant, self.font_family)

        lstrip_text = token.text.lstrip(" ")
        rstrip_text = token.text.rstrip(" ")

        pre_whitespace = len(token.text) - len(lstrip_text)
        post_whitespace = len(token.text) - len(rstrip_text)

        split_text = token.text.split()

        for index, word in enumerate(split_text):
            w = font.measure(word)
            if self.cursor_x + w > self.canvas_width - HSTEP:
                self.flush()

            if index == 0:
                # Ensure pre-text whitespaces are added back
                self.cursor_x += pre_whitespace * font.measure(" ")

            self.line.append((self.cursor_x, word, font, self.current_modifier))

            if index + 1 < len(split_text):
                # Add space between all words within text
                self.cursor_x += w + font.measure(" ")
            else:
                # Ensure post-text whitespaces are added back, could be 0
                self.cursor_x += w + font.measure(" ") * post_whitespace

    def flush(self):
        if not self.line: return
        metrics = [font.metrics() for x, word, font, modifier in self.line]
        max_ascent = max(metric["ascent"] for metric in metrics)
        baseline = self.cursor_y + DEFAULT_LEADING * max_ascent

        for x, word, font, modifier in self.line:
            base_ascent = font.metrics('ascent')

            modifier_offset = 0
            if modifier:
                new_font = font.copy()
                new_font.config(size=int(font.actual('size') / 1.5))
                modifier_offset = new_font.metrics('descent')
                if modifier == FONT_MODIFIERS["superscript"]:
                    word_y_offset = baseline - base_ascent - modifier_offset
                    self.display_list.append((x, word_y_offset, word, new_font))
                elif modifier == FONT_MODIFIERS["subscript"]:
                    word_y_offset = baseline - modifier_offset
                    self.display_list.append((x, word_y_offset, word, new_font))
            else:
                word_y_offset = baseline - base_ascent
                self.display_list.append((x, word_y_offset, word, font))

        self.cursor_x = HSTEP
        self.line = []

        max_descent = max(metric["descent"] for metric in metrics)
        self.cursor_y = baseline + DEFAULT_LEADING * max_descent
class Browser:
    SCROLL_STEP = 100

    def __init__(self):
        self.display_list = []
        self.body = ""
        self.body_tokens = []
        self.h_step = HSTEP
        self.v_step= VSTEP

        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window, 
            width=WIDTH,
            height=HEIGHT
        )

        self.document = {
            "height": HEIGHT,
            "width": WIDTH,
        }

        self.canvas.pack(fill='both', expand=True)

        self.font = tkinter.font.Font(
            family="Times",
            size=16,
            weight="normal",
            slant="roman",
        )

        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<MouseWheel>", self.mouse_scroll)
        self.window.bind("<plus>", self.zoomin)
        self.window.bind("<minus>", self.zoomout)
        self.window.bind("<Configure>", self.resize)

        self.scroll = 0
        self.mode = BROWSER_MODES["normal"]
        self.draw_count = 0

    def mouse_scroll(self, event):
        self.scroll -= event.delta * 3

        if self.scroll < 0:
            self.scroll = 0
        self.draw()

    def resize(self, event):
        if (event.width != self.document["width"] or event.height != self.document["height"]) and self.display_list:
            if event.width != self.document["width"]:
                self.display_list = Layout(self.body_tokens, self.font, event.width).display_list
            self.document = {
                "height": event.height,
                "width": event.width,
            }
            self.draw()

    def scrolldown(self, event):
        self.scroll += Browser.SCROLL_STEP
        self.draw()

    def scrollup(self, event):
        self.scroll -= Browser.SCROLL_STEP
        if self.scroll < 0:
            self.scroll = 0
        self.draw()

    def zoomin(self, event):
        self.font.config(size=int(self.font.actual('size') * 1.2))
        self.display_list = Layout(self.body_tokens, self.font, self.document["width"]).display_list
        self.draw()
    
    def zoomout(self, event):
        next_font_size = int(self.font.actual('size') / 1.2) if int(self.font.actual('size') / 1.2) > 9 else 9
        self.font.config(size=next_font_size)
        self.display_list = Layout(
            self.body_tokens,
            self.font,
            self.document["width"]
            ).display_list
        self.draw()

    def draw(self):
        self.canvas.delete("all")
        for x, y, c, font in self.display_list:
            if y > self.scroll + self.document["height"]:
                continue # below view
            if y + font.metrics('linespace') < self.scroll: 
                continue # above view
            self.canvas.create_text(x, y - self.scroll, text=c, font=font, anchor="nw")

    def load(self, url):
        if url.startswith('view-source:'):
            self.mode = BROWSER_MODES["source"]
            _, url = url.split(":", 1)
            headers, body = request(url)
            body = body.replace("<", "&lt;").replace(">", "&gt;")
            self.body_tokens = HTMLParser(body).parse()
            self.display_list = Layout(self.body_tokens, self.font, self.document["width"]).display_list
            self.draw()
        else:
            self.mode = BROWSER_MODES["normal"]
            headers, body = request(url)
            self.body_tokens = HTMLParser(body).parse()
            self.body_tokens.visualize()
            self.display_list = Layout(self.body_tokens, self.font, self.document["width"]).display_list
            self.draw()

if __name__ == "__main__":
    import sys
    Browser().load(sys.argv[1])
    tkinter.mainloop()

