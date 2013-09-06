#!/usr/bin/env python

"""This will read a file containing newline-separated strings, each of
which is a repr of a an iterator of one or more metrics.

It'll pickle the output of that repr, and send it to the remote side.
Usage:
repr_pickle_sender.py <host> <port> <filename>

This will write metric data to fd 0 in the form of:
<number of metrics>,<number of bytes>,<time taken to send>

XXX it would be useful to gracefully handle signals, e.g. being able
to get a TERM, and so return stats at the time of the TERM.  Currently
if we take too long, we'll just get killed by the queue-runner

This is simpler than nc https://github.com/pcn/carbon/issues/16.
"""

import os
import sys
import struct
import cPickle as pickle
import time
import socket

fname = sys.argv[3]
f = open(fname)

struct_format = "!I"

f.seek(-1, 2)
size = f.tell()
f.seek(0)

if size == 0:
    # print "DEBUG: File {0} is zero length, removing it".format(fname)
    os.unlink(fname)
    sys.exit(1) # 1 will mean no data

# print("DEBUG: Sending {0} bytes with {1}".format(size, sys.argv))
timeout      = 10
try:
    conn = socket.create_connection((sys.argv[1], sys.argv[2],), timeout)
except Exception as e:
    print "ERROR: Trying to connect to the remote: {0}:{1}".format(sys.argv[1], sys.argv[2])
    print "ERROR: message is {0}".format(str(e))
    print "ERROR: exiting."
    sys.exit(100)

start_time   = time.time()
metric_count = 0
errored      = False
for line in f:
    try:
        l = eval(line)
        p = pickle.dumps(l, protocol=-1)
        metric_count += len(l)
    except TypeError as te:
        print "ERROR: TypeError trying to pickle '{0}'".format(line)
        errored = True
        continue
    except SyntaxError as se:
        print "ERROR: SyntaxError trying to pickle '{0}'".format(line)
        errored = True
        continue
    try:
        conn.sendall(struct.pack(struct_format, len(p)) + p)
    except Exception as another_error:
        print "ERROR: IOError trying to send {0}: {1}".format(fname, l)
        print "ERROR: the message is: {0}".format(str(another_error))
        print "ERROR: exiting."
        sys.exit(100)

end_time           = time.time()
time_taken         = end_time - start_time
bytes_per_second   = float(size) / float(time_taken)
metrics_per_second = float(metric_count) / float(time_taken)

# if called from the command line, this may fail.  If called from
# queue-runner.py, this should succeed.
try:
    os.write(0, "{0:.2f},{1:.2f},{2:.6f}".format(
        float(metric_count), float(size), float(time_taken)))
except OSError:
    print("INFO: {0} sent {1} bytes for {2} metrics in {3} second(s) ({4} bytes/second, {5} metrics/second) from {6}".format(
        os.path.basename(sys.argv[0]), size, metric_count, time_taken, bytes_per_second, metrics_per_second, fname))

# XXX add a rename() to a file that the queue dispatcher will ignore instead
# of an unlink here.  -PN
os.unlink(sys.argv[3])