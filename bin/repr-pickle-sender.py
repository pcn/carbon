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

"""

import os
import sys
import struct
import cPickle as pickle
import subprocess
import time

def exit_if_too_small(size, fname):
    """Exit if the file is zero bytes"""
    if size == 0:
        # print "DEBUG: File {0} is zero length, removing it".format(fname)
        os.unlink(fname)
        sys.exit(1) # 1 will mean no data
def process_and_send_file(f, sub_p):
    """Iterates through the file, and sends all parseable lines via
    the sub_process provided in sub_p
    """
    struct_format = "!I"
    metric_count = 0
    for line in f:
        try:
            l = eval(line)
            p = pickle.dumps(l, protocol=-1)
            metric_count += len(l)
        except TypeError as te:
            print "ERROR: TypeError trying to pickle '{0}'".format(line)
            continue
        except SyntaxError as se:
            print "ERROR: SyntaxError trying to pickle '{0}'".format(line)
            continue
        try:
            sub_p.stdin.write(struct.pack(struct_format, len(p)) + p)
        except IOError:
            break # No child, get out of here
    sub_p.terminate()
    return metric_count

def main(argv=sys.argv[:]):
    fname         = argv[3]
    start_time    = time.time()
    metric_count  = 0
    f             = open(fname)

    f.seek(-1, 2)
    size = f.tell()
    f.seek(0)

    # We can receive metrics whose values are "Infity", e.g.:
    # Platform2.Superman.RecommendationService.i-a50645c5.internal.actors.ratio-output-vs-input.StaticUrgencyTickHistorian.gauge.value Infinity 1374043609
    #
    # set inf=-1 for right now since it's not OK
    inf=-1
    exit_if_too_small(size, fname)
    sub_p = subprocess.Popen(['nc', sys.argv[1], sys.argv[2]],
                             stdin=subprocess.PIPE)

    metric_count = process_and_send_file(f, sub_p)

    # print("DEBUG: Sending {0} bytes with {1}".format(size, argv))
    end_time = time.time()
    time_taken = end_time - start_time
    bytes_per_second = float(size) / float(time_taken)
    metrics_per_second = float(metric_count) / float(time_taken)
    # if called from the command line, this may fail.  If called from
    # queue-runner.py, this should succeed.
    try:
        os.write(0, "{0:.2f},{1:.2f},{2:.6f}".format(
            float(metric_count), float(size), float(time_taken)))
    except OSError:
        print("INFO: {0} sent {1} bytes for {2} metrics in {3} second(s) ({4} bytes/second, {5} metrics/second) from {6}".format(
            os.path.basename(sys.argv[0]), size, metric_count, time_taken, bytes_per_second, metrics_per_second, fname))

    os.unlink(sys.argv[3])

if __name__ == '__main__':
    main()