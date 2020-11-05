import telnetlib
import sys
import os

if len(sys.argv) != 5:
    print("Usage: %s host_ip user password prompt" % sys.argv[0])
    sys.exit(1)

host_ip = sys.argv[1]
user = sys.argv[2]
password = sys.argv[3]
prompt = sys.argv[4]

try:
    tn = telnetlib.Telnet(host_ip)
except Exception:
    print("Connection refused")
    sys.exit(1)
output = tn.read_until('login:', 30)
if not output.strip():
    print("Connection timed out")
    sys.exit(1)
tn.write(user)
tn.write(os.linesep)
output = tn.read_until('Password:', 10)
tn.write(password)
tn.write(os.linesep)
output += tn.read_until(prompt, 5)
if "Login incorrect" in output:
    print("Login incorrect")
    sys.exit(1)
tn.write("quit")
tn.write(os.linesep)
print(output)
