from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

# HD Video Streaming:
# - RTP/UDP thường nên giới hạn payload ~1400 bytes để tránh IP fragmentation
# (vì MTU Ethernet ~1500, trừ header IP/UDP/RTP).
# Nếu frame JPEG lớn hơn ngưỡng này -> phải "cắt nhỏ" frame ra nhiều gói RTP
MAX_RTP_PAYLOAD = 1400  # payload tối đa cho mỗi gói RTP (HD streaming)
 
class ServerWorker:
    # Các RTSP method mà client gửi lên (RTSP request)
	SETUP = 'SETUP'
	PLAY = 'PLAY'
	PAUSE = 'PAUSE'
	TEARDOWN = 'TEARDOWN'
	
	# Trạng thái phiên RTSp
	INIT = 0  # chưa SETUP
	READY = 1 # Đã setup, sẵn sàng PLAY
	PLAYING = 2 # đang gửi RTP packets
 
	# Lưu trạng thái hiện tại (mặc định là INIT)
	state = INIT

	OK_200 = 0
	FILE_NOT_FOUND_404 = 1
	CON_ERR_500 = 2
	
	# clientInfo: dict lưu toàn bộ thông tin liên quan đến 1 client session
	# Các key thường gặp:
	# 'rtspSocket': tuple (connSocket, clientAddr)
			# + connSocket: socket TCP dùng để gửi/nhận RTSP
			# + clientAddr: (ip, port) của client phía RTSP
	# session: session id RTSP (server tạo random)
	# videoStream: đối tượng VideoStream để đọc frame JPEG
	# rtpPort: cổng UDP phía client để server gửi RTP tới
	# 'rtpSocket': socket UDP phía server dùng để sendto RTP
	# 'event': threading.Event để báo dừng (PAUSE/TEARDOWN)
	# 'worker': thread đang chạy sendRtp()
	clientInfo = {}
	
	def __init__(self, clientInfo):
		# Nhận clientInfo từ Server.py/ServerWorker creator
		self.clientInfo = clientInfo
		
	def run(self):
		# Tạo thread riêng để lắng nghe RTSP request (TCP)
		threading.Thread(target=self.recvRtspRequest).start()
	
	def recvRtspRequest(self):
		"""Receive RTSP request from the client qua TCP (rtspSocket)"""
		connSocket = self.clientInfo['rtspSocket'][0]
		while True:            
			data = connSocket.recv(256)
			# nếu có dữ liệu thì decode và chuyển qua xử lý
			if data:
				print("Data received:\n" + data.decode("utf-8"))
				self.processRtspRequest(data.decode("utf-8"))
	
	def processRtspRequest(self, data):
		"""Process RTSP request sent from the client."""
		# Get the request type
		request = data.split('\n')
		line1 = request[0].split(' ')
		requestType = line1[0] # SETUP/PLAY/PAUSE/TEARDOWN
		
  		# Get the media file name
		filename = line1[1]
		
		# Get the RTSP sequence number 
		seq = request[1].split(' ')
		
		# Process SETUP request
		if requestType == self.SETUP:
			if self.state == self.INIT:
				# Update state
				print("processing SETUP\n")
				
				try:
					# Tạo VideoStream để đọc frame 
					self.clientInfo['videoStream'] = VideoStream(filename)
					self.state = self.READY
				except IOError:
					# Không mở được file -> báo lỗi 404
					self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
					return 			
    
				# Generate a randomized RTSP session ID
				self.clientInfo['session'] = randint(100000, 999999)
				
				# Send RTSP reply
				self.replyRtsp(self.OK_200, seq[1])
				
				# Get the RTP/UDP port from the last line
				self.clientInfo['rtpPort'] = request[2].split(' ')[3]
		
		# Process PLAY request 		
		elif requestType == self.PLAY:
			if self.state == self.READY:
				print("processing PLAY\n")
				self.state = self.PLAYING
				
				# Create a new socket for RTP/UDP
				self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				
				self.replyRtsp(self.OK_200, seq[1])
				
				# Create a new thread and start sending RTP packets
				self.clientInfo['event'] = threading.Event()
				self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
				self.clientInfo['worker'].start()
		
		# Process PAUSE request
		elif requestType == self.PAUSE:
			if self.state == self.PLAYING:
				print("processing PAUSE\n")
				self.state = self.READY
				
				self.clientInfo['event'].set()
			
				self.replyRtsp(self.OK_200, seq[1])
		
		# Process TEARDOWN request
		elif requestType == self.TEARDOWN:
			print("processing TEARDOWN\n")
   
			# Chỉ set event nếu đã từng PLAY
			if 'event' in self.clientInfo:
				self.clientInfo['event'].set()
			
			self.replyRtsp(self.OK_200, seq[1])
			
			# Chỉ close nếu socket đã được tạo
			if 'rtpSocket' in self.clientInfo:
				try:
					self.clientInfo['rtpSocket'].close()
				except:
					pass
 
			self.state = self.INIT
			
	def sendRtp(self):
		"""Send RTP packets over UDP."""
		while True:
			self.clientInfo['event'].wait(0.05) 
			
			# Stop sending if request is PAUSE or TEARDOWN
			if self.clientInfo['event'].isSet(): 
				break 
				
			data = self.clientInfo['videoStream'].nextFrame()
			if data: 
				frameNumber = self.clientInfo['videoStream'].frameNbr()
				try:
					address = self.clientInfo['rtspSocket'][1][0]
					port = int(self.clientInfo['rtpPort'])
     
					# chỗ chỉnh sửa cho HD Video Streaming
					if len(data) <= MAX_RTP_PAYLOAD:
						# Giữ behaviour cũ: 1 frame = 1 packet
						packet = self.makeRtp(data, frameNumber, marker=1)
						self.clientInfo['rtpSocket'].sendto(packet, (address, port))
					else:
						# HD: frame quá lớn → gửi nhiều packet
						self.sendFragmentedFrame(data, frameNumber, address, port)
				except:
					print("Connection Error")
					#print('-'*60)
					#traceback.print_exc(file=sys.stdout)
					#print('-'*60)

	# Thêm marker = 0 vào makeRtp for HD Video Streaming
	def makeRtp(self, payload, frameNbr, marker = 0):
		"""RTP-packetize the video data."""
		version = 2
		padding = 0
		extension = 0
		cc = 0
		pt = 26 # MJPEG type
		seqnum = frameNbr
		ssrc = 0 
		
		rtpPacket = RtpPacket()
		
		rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
		
		return rtpPacket.getPacket()
		
	def replyRtsp(self, code, seq):
		"""Send RTSP reply to the client."""
		if code == self.OK_200:
			#print("200 OK")
			reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
			connSocket = self.clientInfo['rtspSocket'][0]
			connSocket.send(reply.encode())
		
		# Error messages
		elif code == self.FILE_NOT_FOUND_404:
			print("404 NOT FOUND")
		elif code == self.CON_ERR_500:
			print("500 CONNECTION ERROR")
   
	# Helper for HD video streaming: def makeRtp
	def sendFragmentedFrame(self, data, frameNbr, address, port):
		"""HD: Gửi một frame lớn bằng nhiều gói RTP (fragmentation)."""
		total = len(data)
		offset = 0

		while offset < total:
			chunk = data[offset: offset + MAX_RTP_PAYLOAD]
			offset += MAX_RTP_PAYLOAD

            # marker = 1 nếu là fragment cuối của frame
			marker = 1 if offset >= total else 0

			packet = self.makeRtp(chunk, frameNbr, marker=marker)
			self.clientInfo['rtpSocket'].sendto(packet, (address, port))
