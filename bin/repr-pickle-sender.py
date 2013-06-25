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

f = open(sys.argv[3])

struct_format = "!I"

f.seek(-1, 2)
size = f.tell()
f.seek(0)

sub_p = subprocess.Popen(['nc', sys.argv[1], sys.argv[2]],
                         stdin=subprocess.PIPE)
print "GOING TO SEND {0} bytes with {1}".format(size, sys.argv)
for line in f:
    p = pickle.dumps(eval(line), protocol=-1)
    # The documentation for subprocess warns about writing
    # directly to the stdin object because of the possibility of
    # pipes blocking.
    #
    # I may have to make this block on select indicating the pipe
    # is free in the future, this may fail as it is now.  However,
    # I don't think there's a high chance of a deadlock since the
    # output from nc is going towards a network socket.
    sub_p.stdin.write(struct.pack(struct_format, len(p)) + p)

os.unlink(sys.argv[3])