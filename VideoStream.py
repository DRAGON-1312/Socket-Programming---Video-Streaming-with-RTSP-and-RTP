class VideoStream:
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
  
		# Detect file format: lab (length+JPEG) vs raw MJPEG (SOI/EOI)
		# Lab format {movie.Mjpeg}: 5 byte ASCII độ dài + JPEG frame
		# MJPEG samples (720p/1080p): chuỗi JPEG nối tiếp, phân cách bởi
		# SOI (0xFFD8) và EOI (0xFFD9).
		peek = self.file.read(5)
		self.mode = "lab"
		self.data = None # dùng cho chế độ mjpeg
		self._offset = 0        # offset hiện tại trong self.data (mjpeg)
  
		if not peek:
			return

		try:
			peek_txt = peek.decode("ascii")
		except UnicodeDecodeError:
			peek_txt = ""
   
		if peek_txt.isdigit():
			# Định dạng lab movie.Mjpeg -> giữ file handle, quay lại đầu.
			self.mode = "lab"
			self.file.seek(0)
		else:
			# Định dạng raw MJPEG -> đọc hết vào bộ nhớ cho đơn giản.
			self.mode = "mjpeg"
			remainder = self.file.read()
			self.file.close()
			self.file = None
			self.data = peek + remainder
			self._offset = 0

	# Helpers for Extend the system to stream 720p or 1080p
	def _nextFrame_lab(self):
		"""Đọc frame theo format lab movie.Mjpeg:
        [5 ASCII length][JPEG frame bytes]...
        """
		data = self.file.read(5) # Get the framelength from the first 5 bits
		if not data:
			return b''
		framelength = int(data)
		data = self.file.read(framelength)
		self.frameNum += 1
		return data

	def _nextFrame_mjpeg(self):
		"""Đọc frame từ raw MJPEG (các JPEG nối tiếp nhau).
        Frame được phân cách bằng SOI (0xFFD8) và EOI (0xFFD9).
        """
		if self.data is None:
			return b""

		SOI = b'\xff\xd8'
		EOI = b'\xff\xd9'
  
		data = self.data

		# Tìm SOI từ vị trí hiện tại
		start = data.find(SOI, self._offset)
		if start == -1:
			return b""

		# Tìm EOI sau SOI
		end = data.find(EOI, start + 2)
		if end == -1:
			return b""

		end += 2	# include marker EOI
		frame = data[start:end]
  		
		# Cập nhật offset cho lần đọc sau
		self._offset = end
		self.frameNum += 1
		return frame
		
	def nextFrame(self):
		if self.mode == 'lab':
			return self._nextFrame_lab()
		else:
			return self._nextFrame_mjpeg()
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	