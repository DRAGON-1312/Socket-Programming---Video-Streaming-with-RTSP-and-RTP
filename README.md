# Project: SOCKET PROGRAMMING - VIDEO STREAMING

This is an implementation of a simple RTSP (control) + RTP (data) video streaming system. It demonstrates how a server can stream MJPEG video over RTP/UDP while the client controls playback with RTSP over TCP.

## Quick summary
- **Server**: Listens for RTSP connections, serves MJPEG-style video, packetizes frames into RTP packets, and streams to the client's RTP port over UDP.
- **Client**: Send RTSP requests (SETUP, PLAY, PAUSE, TEARDOWN), receives RTP packets, reconstructs JPEG frames, and displays them.

## Prerequisites
- **Python 3.7+**
- Dependencies from `requirements.txt` (Pillow is required for image handling). Install with:

```powershell
python -m pip install -r requirements.txt
```

## Run Server
1. Start the server on a chosen port (example `8554`):

```powershell
python Server.py 8554
```

The server will listen for incoming RTSP/TCP connections and will spawn a worker per client.

## Run Client
1. Launch the client with server address, RTSP port, RTP port (local UDP port to receive RTP), and video filename. Example:

```powershell
python ClientLauncher.py 127.0.0.1 8554 25000 movie.Mjpeg
```

2. The client opens a small Tkinter window with buttons: `Setup`, `Play`, `Pause`, `Teardown`.

Notes:
- The client uses RTSP over TCP to control the session and binds a local UDP port to receive RTP packets.
- The sample video file `movie.Mjpeg` (lab format) and `sample_1280x720.Mjpeg` (raw MJPEG) are small example inputs.

**Files & Purpose**
- `Server.py`: Main server process; accepts RTSP/TCP connections and hands them to `ServerWorker`.
- `ServerWorker.py`: Handles one client session: parses RTSP requests, replies, and sends RTP packets (supports fragmentation for large frames).
- `Client.py`: Tkinter-based client that implements RTSP client logic, receives RTP, reconstructs frames, and displays them.
- `ClientLauncher.py`: Small wrapper to parse CLI args and create the `Client` GUI.
- `VideoStream.py`: Reads frames from either lab-formatted `.Mjpeg` (length-prefixed frames) or raw MJPEG concatenation.
- `RtpPacket.py`: RTP packet helper class (encode/decode RTP header + payload).
- `RtpPacket.py` and server/client code include basic extensions for handling HD frames by fragmenting large frames across multiple RTP packets. The marker bit is used to indicate the last packet of a frame.

**Key Features & Implementation Notes**
- RTSP methods supported: `SETUP`, `PLAY`, `PAUSE`, `TEARDOWN`.
- RTP packetization: frames are packetized as RTP packets. For large HD frames the server fragments a single frame into multiple RTP packets (max payload around 1400 bytes) and sets the RTP marker bit on the last fragment.
- Client-side: Implements a small pre-buffer/cache and smooth-playback timing to help with higher-resolution video.
- The client writes each received frame temporarily to a cache file `cache-<sessionId>.jpg` before loading it into Tkinter to avoid Windows file-lock issues.

**Troubleshooting & Tips**
- If the client fails to display frames, ensure the client RTP port is reachable (no firewall blocks) and not in use.
- Use localhost (`127.0.0.1`) for local testing on the same machine.
- If you see `PermissionError` when deleting cache files on Windows, wait a moment or close the client window; the client attempts to remove temporary cache files on teardown but Windows locks can interfere.

**Extending / Educational Uses**
- This project is suitable as a learning tool for socket programming, real-time transport basics, and multimedia streaming concepts (RTP/RTSP, fragmentation, marker bit semantics).
- Improvements that can be added: proper RTP timestamp handling (synchronization), jitter buffering, secure transport, and support for other codecs/containers.

**License & Contribution**
- This repository contains example/educational code. Feel free to open issues or pull requests with improvements or bug fixes.

If you'd like, I can also:
- add a short demo script to run server+client locally,
- or run a quick lint/test pass and confirm the client/server run on your machine.
