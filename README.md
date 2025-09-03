# socks-python

A minimal SOCKS server implementation written in Python

## Features

- No external dependencies
- Ultra lightweight
- Cross-platform
- SOCKS4 is supported
- SOCKS4a is supported
- SOCKS5 no-auth method (`0x00`) is supported
- SOCKS5 connect is supported
- SOCKS5 UDP associate is supported

## Examples

```bash
#Run the server
PYTHON_LOG=debug python3 server.py --bind 127.0.0.1 1080
```

## License

Licensed under MIT License ([LICENSE](LICENSE))
