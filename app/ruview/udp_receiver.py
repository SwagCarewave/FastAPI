import asyncio
import socket

UDP_IP = "0.0.0.0"
UDP_PORT = 5005


async def udp_receiver():
    loop = asyncio.get_event_loop()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((UDP_IP, UDP_PORT))
    sock.setblocking(False)

    print(f"[UDP] Listening on {UDP_IP}:{UDP_PORT}...")

    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 65535)
            raw_str = data.decode("utf-8", errors="ignore")
            print(f"\n[UDP] FROM: {addr}")
            print(raw_str[:300])
        except Exception as e:
            print(f"[UDP] Error: {e}")
            await asyncio.sleep(1)
