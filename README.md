# Test 4 điểm đầu: 8554 - RTSP_port
Terminal 1: python Server.py 8554
# 8553: server port and 9999: RTP_port
Terminal 2: python ClientLauncher.py 127.0.0.1 8554 9999 movie.Mjpeg

# Test 720p for HD Video Streaming: 
python ClientLauncher.py 127.0.0.1 8554 9999 sample_1280x720.Mjpeg