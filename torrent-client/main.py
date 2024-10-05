import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import psutil
from torrent_downloader import TorrentDownloader
from profile_image_processor import ProfileImageProcessor

torrent_port = sys.argv[1]
http_port = sys.argv[2]
rpc_password = sys.argv[3]
start_download_payload = sys.argv[4]

torrent_downloader = None

try:
    if start_download_payload:
        initial_download = json.loads(urllib.parse.unquote(start_download_payload))
        torrent_downloader = TorrentDownloader(torrent_port)
        torrent_downloader.start_download(initial_download['game_id'], initial_download['magnet'], initial_download['save_path'])
except (json.JSONDecodeError, KeyError, ValueError) as e:
    sys.stderr.write(f"Failed to start torrent download: {e}\n")

class Handler(BaseHTTPRequestHandler):
    rpc_password_header = 'x-hydra-rpc-password'

    skip_log_routes = [
        "process-list",
        "status"
    ]

    def log_error(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format % args))

    def log_message(self, format, *args):
        for route in self.skip_log_routes:
            if route in args[0]:
                return
        super().log_message(format, *args)

    def do_GET(self):
        try:
            if self.path == "/status":
                if self.headers.get(self.rpc_password_header) != rpc_password:
                    self.send_response(401)
                    self.end_headers()
                    return

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()

                status = torrent_downloader.get_download_status()
                self.wfile.write(json.dumps(status).encode('utf-8'))

            elif self.path == "/healthcheck":
                self.send_response(200)
                self.end_headers()

            elif self.path == "/process-list":
                if self.headers.get(self.rpc_password_header) != rpc_password:
                    self.send_response(401)
                    self.end_headers()
                    return

                process_list = [proc.info for proc in psutil.process_iter(['exe', 'pid', 'username'])]

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()

                self.wfile.write(json.dumps(process_list).encode('utf-8'))
        except Exception as e:
            sys.stderr.write(f"Error in GET request: {e}\n")
            self.send_response(500)
            self.end_headers()

    def do_POST(self):
        global torrent_downloader
        try:
            if self.headers.get(self.rpc_password_header) != rpc_password:
                self.send_response(401)
                self.end_headers()
                return

            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            if self.path == "/profile-image":
                parsed_image_path = data['image_path']
                try:
                    parsed_image_path, mime_type = ProfileImageProcessor.process_image(parsed_image_path)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({'imagePath': parsed_image_path, 'mimeType': mime_type}).encode('utf-8'))
                except Exception as e:
                    sys.stderr.write(f"Error processing profile image: {e}\n")
                    self.send_response(400)
                    self.end_headers()

            elif self.path == "/action":
                if torrent_downloader is None:
                    torrent_downloader = TorrentDownloader(torrent_port)

                if data['action'] == 'start':
                    try:
                        torrent_downloader.start_download(data['game_id'], data['magnet'], data['save_path'])
                    except Exception as e:
                        sys.stderr.write(f"Error starting torrent: {e}\n")
                        self.send_response(500)
                        self.end_headers()
                        return

                elif data['action'] == 'pause':
                    try:
                        torrent_downloader.pause_download(data['game_id'])
                    except Exception as e:
                        sys.stderr.write(f"Error pausing torrent: {e}\n")
                        self.send_response(500)
                        self.end_headers()
                        return

                elif data['action'] == 'cancel':
                    try:
                        torrent_downloader.cancel_download(data['game_id'])
                    except Exception as e:
                        sys.stderr.write(f"Error canceling torrent: {e}\n")
                        self.send_response(500)
                        self.end_headers()
                        return

                elif data['action'] == 'kill-torrent':
                    try:
                        torrent_downloader.abort_session()
                        torrent_downloader = None
                    except Exception as e:
                        sys.stderr.write(f"Error killing torrent: {e}\n")
                        self.send_response(500)
                        self.end_headers()
                        return

                self.send_response(200)
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            sys.stderr.write(f"Error in POST request: {e}\n")
            self.send_response(500)
            self.end_headers()

if __name__ == "__main__":
    try:
        httpd = HTTPServer(("", int(http_port)), Handler)
        sys.stderr.write(f"Server running on port {http_port}\n")
        httpd.serve_forever()
    except Exception as e:
        sys.stderr.write(f"Failed to start HTTP server: {e}\n")
