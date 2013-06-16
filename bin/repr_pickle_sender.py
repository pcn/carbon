#!/usr/bin/env python

"""This will read a file containing newline-separated strings, each of
which is a repr of a an iterator of one or more metrics.

It'll pickle the output of that repr, and send it to the remote side.
"""

import os
import sys
import struct
import cPickle as pickle
import subprocess

f = open(sys.argv[3])

struct_format = "!I"

sub_p = subprocess.Popen(['nc', sys.argv[1], sys.argv[2]],
                         stdin=subprocess.PIPE)
print "GOING TO SEND {0}".format(sys.argv)
for line in f:
    p = pickle.dumps(eval(line), protocol=-1)
    # The documentation for subprocess warns about writing
    # directly to the stdin object because of the possibility of
    # pipes blocking.
    #
    # I may have to make this block on select indicating the pipe
    # is free in the future, this may fail as it is now.  Until then...
    sub_p.stdin.write(struct.pack(struct_format, len(p)) + p)

os.unlink(sys.argv[3])