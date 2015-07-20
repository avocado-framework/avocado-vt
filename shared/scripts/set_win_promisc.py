import socket
import time
HOST = socket.gethostbyname(socket.gethostname())
s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
s.bind((HOST, 0))

s.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
time.sleep(2)
s.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
time.sleep(2)
