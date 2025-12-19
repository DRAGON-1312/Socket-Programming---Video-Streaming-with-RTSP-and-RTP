class VideoStream:
	def __init__(self, filename):
		# Lưu tên file video
		self.filename = filename
  
		# Mở file ở chế độ nhị phân để đọc bytes (JPEG là dữ liệu nhị phân)
		try:
			self.file = open(filename, 'rb')
		except:
			# Nếu mở file lỗi (không tồn tại / không quyền), ném IOError
			raise IOError

		# Bộ đệm số frame đã đọc (frame number)
		self.frameNum = 0
  
		# Detect file format: lab (length+JPEG) vs raw MJPEG (SOI/EOI)
        #
        # 1) Lab format (movie.Mjpeg của bài lab):
        #    Mỗi frame lưu theo cấu trúc:
        #       [5 bytes ASCII độ dài][JPEG bytes...]
        #    Ví dụ: "00123" + 123 bytes JPEG
        #
        # 2) Raw MJPEG samples (720p/1080p):
        #    File chỉ là chuỗi các ảnh JPEG nối tiếp nhau,
        #    phân cách bằng marker:
        #       SOI = 0xFFD8 (Start Of Image)
        #       EOI = 0xFFD9 (End Of Image)
        #
        # Ta đọc trước 5 bytes đầu để đoán định dạng.
		peek = self.file.read(5)
  
		# Mặc định giả sử là lab, sau đó sẽ kiểm tra lại
		self.mode = "lab"
		# Dùng cho chế độ mjpeg (raw MJPEG): sẽ chứa toàn bộ file trong RAM
		self.data = None 
  		# Offset hiện tại trong self.data (vị trí đang đọc tới) cho chế độ mjpeg
		self._offset = 0        
  
		# Nếu file rỗng -> không làm gì thêm
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
	
	