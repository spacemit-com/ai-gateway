#!/usr/bin/env python3
import argparse
import socket
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main():
    parser = argparse.ArgumentParser(description="Serve the AI Gateway console without browser caching.")
    parser.add_argument("port", nargs="?", type=int, default=8326)
    parser.add_argument("--bind", default="::")
    args = parser.parse_args()

    class Server(ThreadingHTTPServer):
        address_family = socket.AF_INET6 if ":" in args.bind else socket.AF_INET

    with Server((args.bind, args.port), NoCacheHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
