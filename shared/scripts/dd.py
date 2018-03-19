import sys
import os


if len(sys.argv) != 3:
    print("Useage: %s path size")

path = sys.argv[1]
size = int(sys.argv[2])

if not os.path.isdir(os.path.dirname(path)):
    os.mkdir(os.path.dirname(path))
writefile = open(path, 'w')
writefile.seek(1024 * 1024 * size)
writefile.write('\x00')
writefile.close()
