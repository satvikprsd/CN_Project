from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"ip":"10.7.22.85", "mac_name":"khushi","backend":"A","status":"ok"}'
                
        etag = '"' + hashlib.md5(body).hexdigest() + '"'

        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "max-age=60")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "max-age=60")
        self.send_header("ETag", etag)
        self.send_header("X-Backend", "A")
        self.end_headers()

        self.wfile.write(body)


print("Server started on 0.0.0.0:3001")
server = HTTPServer(("0.0.0.0", 3001), Handler)
server.serve_forever()