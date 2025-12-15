# tkinter để làm GUI (Graphical User Interface)
from tkinter import *
import tkinter.messagebox
# PIL (pillow) để đọc file JPEG từng frame và hiển thị lên label
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

# RtpPacket là class hỗ trợ parse gói RTP ở client
from RtpPacket import RtpPacket

# Addition for Smooth HD playback with low latency of HD Video Streaming
from time import time, sleep

# Addition for Client-Side Caching
from collections import deque

# CACHE_FILE_NAME + CACHE_FILE_TEXT: mỗi frame nhận được sẽ được ghi ra file tạm cache-<sessionId>.jpg
# rồi mới load lên GUI
CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
    # Mã trạng thái RTSP (state)
	INIT = 0 # : mới mở app, chưa SETUP
	READY = 1 # : đã SETUP xong, video "sẵn sàng phát" nhưng chưa play
	PLAYING = 2 # : đang nhận RTP và phát video
	state = INIT

	# Mã loại request 	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	
	# Initiation..
	"""
	master: cửa sổ TK chính, gán callback self.handler khi user đóng cửa sổ (dấu X).
	createWidgets(): tạo 4 nút và label video
	severAddr, severPort: dùng cho RTSP qua TCP
	rtpPort: cổng UDP mà client sẽ bind (gắn kết) để nhận RTP
	fileName: tên file video yêu cầu (vd movie.Mjpeg)
	rtspSeq: số Cseq của RTSP - mỗi lần gửi request phải tăng 1 (theo đề bài)
	sessionId: lúc đầu = 0, sau khi SETUP thành công thì lấy Session: từ response rồi lưu lại.
	requestSent: nhớ "request RTSP cuối cùng đã gửi là gì" (SETUP/PLAY/PAUSE/TEARDOWN) để khi nhận reply biết phải cập nhật state nào.
	teardownAcked: flag báo đã nhận ACK TEARDOWN, dùng bên thread RTP để biết lúc nào đóng socket UDP.
	connectToServer(): mở Socket TCP tới server, dùng cho toàn bộ RTSP.
	frameNbr: seqnum frame RTP cao nhất đã hiển thị, để bỏ những gói đến trễ.
	"""
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master 
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets() 
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0
  
		# buffer for HD Video Streaming: buffer để ghép nhiều fragment thành 1 frame
		self.frameBuffer = bytearray()
  
		# HD playback timing - thời gian phát lại HD (Smooth HD playback with low latency.)
		self.targetInterval = 0.05	# 20 fps ~ 50ms / frame
		self.lastFrameTime = None 	# thời điểm show frame trước
  
		# Stats for frame loss & network usage
		self.firstSeq = None	# seqNum đầu tiên nhìn thấy
		self.maxSeq = 0			# sepNum lớn nhất
		self.frameDisplayed = 0 # số frame thật sự show lên GUI
		self.totalBytes = 0		# tổng số byte RTP nhận
		self.startTime = None	# thời điểm nhận packet đầu tiên
		self.framesReceived = 0  # số frame nhận được (sau prebuffer) dùng cho thống kê loss
  
		# Advanced: Client-side caching (frame buffer)
		self.enableCache = True		# Bật/tắt tính năng cache
		self.cachePreload = 10			# N: số frame pre-buffer trước khi hiển thị
		self.cacheMaxSize = 50			# Giới hạn kích thước buffer
		self.frameCache = deque(maxlen=self.cacheMaxSize)
		self.cachePrebuffering = False	# True = đang tích lũy N frame đầu tiên
		
  
	# dùng để tạo ra giao diện chính gồm: 4 nút điều khiển và 1 nhãn lớn để hiển thị nội dung phim + Các thành phần được bố trí bằng grid layout để dễ căn chỉnh.
	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3) # padx: khoảng đệm thep chiều ngang (cách mép nút 3 pixel mỗi bên), pady: khoảng đệm theo chiều dọc (cách mép trên và dưới của nút 3 pixel.)
		self.setup["text"] = "Setup" # hiển thị chữ Setup
		self.setup["command"] = self.setupMovie # khi bấm nút sẽ gọi hàm self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2) # Đặt nút vào hàng 1, cột 0 trong lưới (grid layout).
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19) # để hiển thị phim
		# Đặt ở hàng 0, chiếm toàn bộ 4 cột (columnspan=4).
		# sticky=W+E+N+S giúp label co giãn theo cả 4 hướng (trái, phải, trên, dưới).
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		"""Setup button handler."""
		# cho phép SETUP khi đang ở INIT
		if self.state == self.INIT: 
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		# CHẶN INIT: chưa SETUP thì không teardown, không đóng app
		if self.state == self.INIT:
			tkinter.messagebox.showinfo("Not ready", "Please click SETUP before TEARDOWN.")
			return

		# (giữ nguyên phần còn lại)
		if hasattr(self, "playEvent"):
			self.playEvent.set()

		self.sendRtspRequest(self.TEARDOWN)

		cache_path = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		try:
			if os.path.exists(cache_path):
				os.remove(cache_path)
		except PermissionError:
			pass

		self.master.destroy()

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING: # chỉ PAUSE khi đang PLAYING
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY: # chỉ PLAY khi đang ready
			# Create a new thread to listen for RTP packets
			threading.Thread(target=self.listenRtp).start() # tạo thread mới chạy listenRtp() để liên tục nhận gói RTP
			self.playEvent = threading.Event() # event dùng để báo cho thread dừng lại khi PAUSE/TEARDOWN
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
	
	def listenRtp(self):
		"""Listen for RTP packets."""
		while True:
			try:
				data = self.rtpSocket.recv(20480) # nhận các gói RTP
				if data:
					rtpPacket = RtpPacket()
					rtpPacket.decode(data)
     
					currFrameNbr = rtpPacket.seqNum()
					# Dòng này để debug
					# print("Current Seq Num: " + str(currFrameNbr))
     
					# Cập nhật thống kê (frame loss + data rate)
					if self.startTime is None:
						self.startTime = time()
      
					self.totalBytes += len(data)
     
					# CHỈ ĐẾM LOSS KHI KHÔNG PRE-BUFFER
					# cachePrebuffering : True trong giai đoạn [CACHE] Prebuffering, 
					#                     False khi đã bắt đầu [CACHE] Playing from buffer
					if (not self.enableCache) or (not self.cachePrebuffering):
						if self.firstSeq is None:
							# Frame đầu tiên: gán luôn cả firstSeq và maxSeq
							self.firstSeq = currFrameNbr
							self.maxSeq = currFrameNbr
						else:
							# LOSS-DEBUG: nếu seq nhảy lớn hơn maxSeq+1 ⇒ thật sự có frame bị drop trên đường đi
							#if currFrameNbr > self.maxSeq + 1:
								#missing = currFrameNbr - (self.maxSeq + 1)
								#print(
									#f"[LOSS-DEBUG] Missing {missing} frame(s): "
									#f"expected {self.maxSeq + 1}..{currFrameNbr - 1}, got {currFrameNbr}"
								#)

							# Cập nhật maxSeq bình thường
							if currFrameNbr > self.maxSeq:
								self.maxSeq = currFrameNbr
      
					marker = rtpPacket.marker() 	# bit M - dùng cho HD + fragmentation
	
					# Ghép các mảnh thành 1 frame hoàn chỉnh
					if currFrameNbr > self.frameNbr:
						# bắt đầu frame mới
						self.frameNbr = currFrameNbr
						self.frameBuffer = bytearray()
      
					# chỉ ghép các packet thuộc frame hiện tại
					if currFrameNbr == self.frameNbr:
						self.frameBuffer.extend(rtpPacket.getPayload())
      
						# Nếu marker = 1 ⇒ đây là mảnh cuối cùng của frame
						if marker == 1:
							# copy ra bytes để đưa vào cache / ghi file
							fullFrame = bytes(self.frameBuffer)
							print(f"[FRAME DONE] seq={currFrameNbr}")
       
							# ĐẾM SỐ FRAME NHẬN ĐƯỢC (sau pre-buffer) DÙNG CHO THỐNG KÊ LOSS
							if (not self.enableCache) or (not self.cachePrebuffering):
								self.framesReceived += 1

							# CLIENT-SIDE CACHING
							if self.enableCache:
								# Đẩy frame mới vào hàng đợi (buffer phía client)
								self.frameCache.append(fullFrame)

								# Giai đoạn pre-buffer: tích lũy N frame đầu
								if self.cachePrebuffering:
									# Dòng print này để debug
									#print(f"[CACHE] Prebuffering {len(self.frameCache)}/{self.cachePreload}")

									# Lần đầu tiên vào pre-buffer, in 1 dòng để thấy đang bật cache
									if len(self.frameCache) == 1:
										print(f"[CACHE] Enabled – preloading {self.cachePreload} frames before playback")
          
									# chưa đủ N frame → CHỈ tích lũy, KHÔNG hiển thị
									if len(self.frameCache) < self.cachePreload:
										self.frameBuffer = bytearray()
										continue	# ko show, quay lại nhận gói tiếp theo
									else:
										# đủ N frame → tắt pre-buffer, bắt đầu play trong buffer
										self.cachePrebuffering = False
										print(f"[CACHE] Prebuffering done – start playing from buffer")
								else:
									# Dòng print này để debug
									#print(f"[CACHE] Playing from buffer, size={len(self.frameCache)}")
         
									# (in nhẹ 1 lần khi bắt đầu)
									if len(self.frameCache) == self.cachePreload:
										print(f"[CACHE] Playing from buffer, initial size={len(self.frameCache)}")

								# Giai đoạn play trong buffer
								# mỗi lần nhận thêm 1 frame, show frame lâu nhất trong buffer (FIFO)
								if len(self.frameCache) > 0:
									frameToShow = self.frameCache.popleft()
								else:
									# fallback: nếu buffer rỗng (mất gói nhiều) thì show frame vừa nhận
									frameToShow = fullFrame
							else:
								# không bật cache → hành vi cũ: show luôn frame vừa nhận
								frameToShow = fullFrame
	
							# Smooth HD playback
							now = time()
							if self.lastFrameTime is None:
								# frame đầu tiên: show ngay, ghi nhận mốc thời gian
								self.lastFrameTime = now
							else:
								elapsed = now - self.lastFrameTime
								# Nếu frame tới quá sớm → chờ cho đủ targetInterval để giữ FPS ổn định
								if elapsed < self.targetInterval:
									sleep(self.targetInterval - elapsed)
								# cập nhật lại mốc thời gian
								self.lastFrameTime = time()
        
							# Ghi frame ra file cache-<sessionId>.jpg và update GUI
							imageFile = self.writeFrame(frameToShow)
							self.updateMovie(imageFile)

							# Đếm số frame đã show (dùng cho thống kê loss)
							self.frameDisplayed += 1
       
							# chuẩn bị buffer cho frame tiếp theo
							self.frameBuffer = bytearray()
			
			except:	# timeout, socket đóng (TEARDOWN), PAUSE...
				# Stop listening upon requesting PAUSE or TEARDOWN
				if self.playEvent.isSet(): 	# PAUSE / TEARDOWN đã báo dừng
					break
 
				# Upon receiving ACK for TEARDOWN request, close the RTP socket
				if self.teardownAcked == 1:
					self.rtpSocket.shutdown(socket.SHUT_RDWR)
					self.rtpSocket.close()
					break
   
	"""Ghi payload (JPEG) ra file cache-<sessionId>.jpg và trả về tên file."""
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		# Mở xong copy ra bộ nhớ rồi đóng file => không bị Windows giữ lock
		from PIL import Image, ImageTk

		with Image.open(imageFile) as img:
			frame = ImageTk.PhotoImage(img.copy())

		self.label.configure(image=frame, height=288)
		self.label.image = frame
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Connection Failed', 'Connection to \'%s\' failed.' %self.serverAddr)
	
	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""	
		#-------------
		# TO COMPLETE
		#-------------
		
		# Setup request
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = (
				f"SETUP {self.fileName} RTSP/1.0\n"
				f"CSeq: {self.rtspSeq}\n"
				f"Transport: RTP/UDP; client_port= {self.rtpPort}"
			)
			
			# Keep track of the sent request.
			self.requestSent = self.SETUP
		
		# Play request
		elif requestCode == self.PLAY and self.state == self.READY:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = (
				f"PLAY {self.fileName} RTSP/1.0\n"
				f"CSeq: {self.rtspSeq}\n"
				f"Session: {self.sessionId}"
			)
			
			# Keep track of the sent request.
			self.requestSent = self.PLAY
		
		# Pause request
		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = (
				f"PAUSE {self.fileName} RTSP/1.0\n"
				f"CSeq: {self.rtspSeq}\n" 
				f"Session: {self.sessionId}"
			)
			
			# Keep track of the sent request.
			self.requestSent = self.PAUSE
			
		# Teardown request
		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			# Update RTSP sequence number.
			self.rtspSeq += 1
			
			# Write the RTSP request to be sent.
			request = (
				f"TEARDOWN {self.fileName} RTSP/1.0\n"
				f"CSeq: {self.rtspSeq}\n"
				f"Session: {self.sessionId}"
			)
			
			# Keep track of the sent request.
			self.requestSent = self.TEARDOWN
		else:
			return
		
		# Send the RTSP request using rtspSocket.
		self.rtspSocket.send(request.encode())
		
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR) # ngắt cả chiều gửi/nhận
				self.rtspSocket.close() # giải phóng tài nguyên
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						#-------------
						# TO COMPLETE
						#-------------
						# Update RTSP state.
						self.state = self.READY
						
						# Open RTP port.
						self.openRtpPort() 
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
      
						# Reset thống kê cho mỗi lần PLAY (mỗi session xem mới) -> 
						# để mỗi lần bấm PLAY sẽ có 1 bộ stats riêng, không bị dính với lần PLAY trước
						# Khi cache bật, thống kê sẽ bỏ qua hoàn toàn giai đoạn prebuffer (vì lúc đó cachePrebuffering=True + stats đang reset)
						# startTime chỉ bắt đầu lại khi thật sự đếm loss (sau prebuffer)
						self.firstSeq = None
						self.maxSeq = 0
						self.frameDisplayed = 0
						self.totalBytes = 0
						self.startTime = None
						self.lastFrameTime = None
						self.framesReceived = 0
      
						# Client-side caching: reset buffer + bật pre-buffer
						if self.enableCache:
							self.frameCache.clear()
							self.cachePrebuffering = True
       
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
      
						# In thống kê ngay khi server xác nhận PAUSE	
						self.reportStats()
						
						# The play thread exits. A new thread is created on resume.
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						
						# Flag the teardownAcked to close the socket.
						self.teardownAcked = 1 
      
						# In thống kê ngay khi server xác nhận TEARDOWN
						self.reportStats()
      
						# Client-side caching: dọn buffer
						if self.enableCache:
							self.frameCache.clear()
							self.cachePrebuffering = False
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		#-------------
		# TO COMPLETE
		#-------------
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		# Set the timeout value of the socket to 0.5sec
		self.rtpSocket.settimeout(0.5)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(("", self.rtpPort))
		except:
			tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)
   
	# Helper for Thống kê HD: frame loss & network usage
	def reportStats(self):
		"""Print frame loss rate & video data rate"""
		if self.firstSeq is None or self.startTime is None:
			print("[*]No RTP stats available.")		
			return

		totalFrames = self.maxSeq - self.firstSeq + 1
		totalFrames = max(totalFrames, 0)
  
		lostFrames = max(0, totalFrames - self.framesReceived)
  
		lossRate = (lostFrames / totalFrames) if totalFrames > 0 else 0.0
  
		duration = time() - self.startTime
		if duration <= 0:
			byte_rate = 0.0
		else:
			byte_rate = self.totalBytes / duration # bytes per second
   
		print(f"[*]RTP Frame Loss Rate: {lossRate*100:.2f}% "
          f"({lostFrames}/{totalFrames})")	
		print(f"[*]Video data rate: {byte_rate:.0f} bytes/sec")

	"""Hàm này được gọi khi người dùng đóng cửa sổ GUI"""
	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie() # Tạm dừng phim ngay lập tức để tránh tiếp tục phát khi người dùng đang quyết định thoát hay không -> đảm bảo không có luồng (thread) nhận RTP nào chạy ngầm trong lúc hiển thị hộp thoại xác nhận
		if tkinter.messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()
