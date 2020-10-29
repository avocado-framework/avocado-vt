#!/usr/bin/python

import os


mem_fd = open("/proc/meminfo", 'r')
contents = mem_fd.readlines()
mem_fd.close()
freemem = 0
for content in contents:
    if content.count("MemFree"):
        freemem = int(content.split()[1])
        break

int_size = 4
int_count = int(freemem * 256 * 0.8)

occupy_script = """#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

main()
{
  int *p=NULL;
  int count=%s;
  int size=%s;
  p=(int *)calloc(count, size);
  if(p==NULL)
  {
     exit(1);
  }
  int i;
  for(i=0;i<count-10;i++)
  {
    p[i]=0;
  }
  mlock(p, count*size);
  sleep(120);
  munlock(p, count*size);
  free(p);
}
""" % (int_count, int_size)

occupy_fd = open("/tmp/duplicate_pages.c", 'w')
occupy_fd.write(occupy_script)
occupy_fd.close()

# Compile
os.popen("cd /tmp;gcc -o duplicate_pages duplicate_pages.c")
os.popen("cd /tmp;./duplicate_pages &")
