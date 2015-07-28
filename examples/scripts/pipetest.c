#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <sys/wait.h>
#include <linux/unistd.h>
#define _GNU_SOURCE
#define __USE_GNU
#include <sched.h>
#define TV_2_LONG(tv) (tv.tv_sec*1E6+tv.tv_usec)
#define GET_TIME() \
 ({ struct timeval __tv; gettimeofday(&__tv,NULL); TV_2_LONG(__tv); })
#define LOOPS 10000
int c0 = 0, c1 = 1;
int main (int ac, char **av) {
    unsigned long long t0, t1;
    int fd1[2], fd2[2];
    int m = 0, i;
    cpu_set_t set;
    if (ac == 3) {
        c0 = atoi(av[1]);
        c1 = atoi(av[2]);
    }
    CPU_ZERO(&set);
    pipe(fd1);
    pipe(fd2);
    if (!fork()) {
        CPU_SET(c0, &set);
        sched_setaffinity(0, sizeof(set), &set);
        for (;;) {
            t0 = GET_TIME();
            for (i = 0; i < LOOPS; i++) {
                read(fd1[0], &m, sizeof(int));
                m = 2;
                write(fd2[1], &m, sizeof(int));
            }
            t1 = GET_TIME();
            printf("%.2f usecs/loop.\n",
            (double)(t1-t0)/(double)LOOPS);
            fflush(stdout);
        }
    } else {
        CPU_SET(c1, &set);
        sched_setaffinity(0, sizeof(set), &set);
        for (;;) {
            m = 1;
            write(fd1[1], &m, sizeof(int));
            read(fd2[0], &m, sizeof(int));
        }
    }
}
