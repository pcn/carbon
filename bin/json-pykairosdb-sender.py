#!/usr/bin/env python

"""This will read a file containing newline-separated strings, each of
which is a json document containing a list of one or more metrics.

It'll turn the result of evaluating the line/document into individal
items that will be sent it to the destination as line protocol carbon
metrics.

Usage:
json-lineproto-socket-sender.py <host> <port> <filename>

This will write instrumentation data back to fd 0 in the form of:
<number of metrics>,<number of bytes>,<time taken to send>

XXX it would be useful to gracefully handle signals, e.g. being able
to get a TERM, and so return stats at the time of the TERM.  Currently
if we take too long, we'll just get killed by the queue-runner

"""

import os
import sys
import struct
import time
import socket
import json
import gzip
import math
import traceback

import pyKairosDB
from pyKairosDB import graphite as g

import sys
from os.path import dirname, join, abspath

# Figure out where we're installed
BIN_DIR = dirname(abspath(__file__))
ROOT_DIR = dirname(BIN_DIR)

# Make sure that carbon's 'lib' dir is in the $PYTHONPATH if we're running from
# source.
LIB_DIR = join(ROOT_DIR, 'lib')
sys.path.insert(0, LIB_DIR)

import carbon.conf

carbon_conf_options = {'config' : None,
                       'instance' : 'a',
                       'pidfile' : '/dev/null',
                       'logdir' : '/dev/null',
                       'CONF_DIR' : ROOT_DIR + "/conf"
}

settings = carbon.conf.read_config('cache',
                                   carbon_conf_options,
                                   ROOT_DIR=ROOT_DIR,
                                   )

# loadStorageSchemas needs a settings hash to be available in
# carbon.conf.settings, so in order to get the storage schemas we need
# to initialize it to a sane state.  Maybe there's a better way?
# Dunno at the moment.
carbon.conf.settings = settings
from carbon.storage import loadStorageSchemas
storage_schemas = loadStorageSchemas()

def kairosdb_batch(input_list):
    """Given a list of metrics, turn them into a list useable by pyKairosDB"""
    return g.graphite_metric_list_with_retentions_to_kairosdb_list(
        yield_lists_of_lines(input_list), storage_schemas)

def yield_lists_of_lines(metric_list):
    """For some weird reason, the line protocol is data then date.  The internal
    representation is date then data.  Oh, well..."""
    return [ (m[0],m[1][0],m[1][1]) for m in metric_list ]


def open_file(filename):
    """Open the file, with support for gzip files whose names end in .gz
    """
    f         = open(filename)
    f.seek(0, 2)
    raw_size  = f.tell()
    f.seek(0)

    if raw_size == 0:
        os.unlink(filename)
        raise ValueError, "{0} is a zero-length file".format(filename)

    if filename.endswith('.gz'):
        return gzip.GzipFile(fileobj=f)
    else:
        return f

def yield_backoff_pattern(count, taper_point = 20, exponent = 1.4):
    """Provide a backoff pattern that retries using an exponential backoff initially,
    then tapers off to a ceiling
    """
    for c in range(1, count):
        if (c ** exponent) > taper_point:
            yield int(taper_point)
        else:
            yield int(c ** exponent)



def write_batch_with_retry(conn, batch, backoff_count = 20):
    backoffs = yield_backoff_pattern(backoff_count)
    for count in backoffs:
        rv = conn.write_metrics(batch)
        if rv.status_code == 500: # Currently we don't have a 503 for retriable errors
            print "status is {0}, sleeping {1}".format(rv, count)
            time.sleep(count)
        else:
            return rv
    raise ValueError, "The KairosDB server has failed to accept after {0} tries".format(backoff_cont)

def yield_batch(file_obj, lines_in_a_batch=5):

    for count in lines_in_batch:
        batch = list()
        for c in range(lines_in_batch):
            batch.extend(file_obj.readline())
        yield kairosdb_batch(batch)

def main():
    # Since we are using gzip files that were appended to when written, we'll need to
    # keep track of the size of the file as we read and send in order to provide
    # decent metrics.
    fname     = sys.argv[3]
    try:
        f = open_file(fname)
    except ValueError as ve:

        sys.exit(1) # 1 will mean no data
    size = 0
    timeout   = 60

    try:
        conn = pyKairosDB.connect(server=sys.argv[1], port=sys.argv[2])
    except Exception as e:
        print "ERROR: Trying to connect to the remote: {0}:{1}".format(sys.argv[1], sys.argv[2])
        print "ERROR: message is {0}".format(str(e))
        print "ERROR: exiting."
        sys.exit(100)

    start_time   = time.time()
    metric_count = 0
    errored      = False

    for batch in yield_batch(conn, 4):
    # for line in f:
        # Counting length of the line, assuming that 1 char == 1 byte which
        # will probably break in python3 or if the line is somehow
        # unicode in 2.x
        size += len(line) # before parsing, just # of chars
        try:
            loaded_metrics = json.loads(line)
            metric_count += len(loaded_metrics)
        except TypeError as te:
            print "ERROR: TypeError trying to read '{0}'".format(line)
            errored = True
            continue
        except ValueError as ve:
            print "ValueError: there is a problematic line in {0}".format(line)
            print "ValueError: the message is {0}".format(str(ve))

        try:
            # batch = list(kairosdb_batch(loaded_metrics))
            write_batch_with_retry(conn, batch)
            time.sleep(0.01)
        except Exception as another_error:
            print "ERROR: Some other error trying to send {0}".format(fname)
            print "ERROR: the message is: {0}".format(str(another_error))
            traceback.print_exc()
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

    os.unlink(sys.argv[3])

if __name__ == '__main__':
    main()
