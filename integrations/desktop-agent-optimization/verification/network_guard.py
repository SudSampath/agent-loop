"""Deny outbound fixture connections except one explicit loopback mock port."""

import ipaddress
import socket


def loopback_host(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_destination(address, allowed_port):
    if not isinstance(address, tuple) or len(address) < 2:
        raise OSError('Fixture network guard rejected an invalid network destination')
    host, port = address[:2]
    if not loopback_host(host) or port != allowed_port:
        raise OSError(f'Fixture network guard blocked a non-mock destination: {host}:{port}')


def install_guard(allowed_port):
    """Install before Headroom imports so auth-based routing cannot escape a mock."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            validate_destination(address, allowed_port)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            validate_destination(address, allowed_port)
        return original_connect_ex(sock, address)

    def getaddrinfo(host, port, *args, **kwargs):
        if not loopback_host(host) or int(port) != allowed_port:
            raise OSError('Fixture network guard blocked non-mock DNS resolution')
        return original_getaddrinfo(host, port, *args, **kwargs)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.getaddrinfo = getaddrinfo
