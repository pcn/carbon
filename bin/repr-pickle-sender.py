#!/usr/bin/env python

"""This will read a file containing newline-separated strings, each of
which is a repr of a an iterator of one or more metrics.

It'll pickle the output of that repr, and send it to the remote side.
Usage:
repr_pickle_sender.py <host> <port> <filename>
"""

import os
import sys
import struct
import cPickle as pickle
import subprocess
import time

fname = sys.argv[3]
f = open(fname)

struct_format = "!I"

f.seek(-1, 2)
size = f.tell()
f.seek(0)

if size == 0:
    print "File {0} is zero length, removing it".format(fname)
    os.unlink(fname)
    sys.exit(1) # 1 will mean no data

sub_p = subprocess.Popen(['nc', sys.argv[1], sys.argv[2]],
                         stdin=subprocess.PIPE)
start_time = time.time()
print("INFO: Sending {0} bytes with {1}".format(size, sys.argv))
metric_count = 0
for line in f:
    try:
        l = eval(line)
        p = pickle.dumps(l, protocol=-1)
        metric_count += len(l)
    except TypeError as te:
        print "ERROR: TypeError trying to pickle '{0}'".format(line)
    # The documentation for subprocess warns about writing
    # directly to the stdin object because of the possibility of
    # pipes blocking.
    #
    # I may have to make this block on select indicating the pipe
    # is free in the future, this may fail as it is now.  However,
    # I don't think there's a high chance of a deadlock since the
    # output from nc is going towards a network socket.
    sub_p.stdin.write(struct.pack(struct_format, len(p)) + p)

sub_p.terminate()
end_time = time.time()
time_taken = end_time - start_time
bytes_per_second = float(size) / float(time_taken)
metrics_per_second = float(metric_count) / float(time_taken)
print("INFO: Sent {0} bytes for {1} metrics in {2} second(s) ({3} bytes/second, {4} metrics/second) from {5}".format(size,
    metric_count, time_taken, bytes_per_second, metrics_per_second, fname))


os.unlink(sys.argv[3])