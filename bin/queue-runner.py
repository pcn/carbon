#!/usr/bin/env python

"""Runs through a queue of graphite-style carbon metrics and
send them.

It does this by picking up files in the send queue directory, and
sending them to the configured endpoint (the dest_host and dest_port
arguments).


"""


import sys
import os
import os.path
import optparse
import time
import resource

def do_fork(dst_host, dst_port, command, filename):
    """Don't wait here, wait and reap children in main()"""
    pid = fork();
    if pid == 0: # child
        os.execvp(command, [command, dst_host, dst_port, filename])
    else:
        return pid

def log_overtime_processes(children):
    now = time.time()
    for p in children.items():
        if p[1][0] > now:
            pass # XXX: to do : log that the process is overtime.
            # And kill it and put the file back on the queue, implicitly.

def pickup_something_from_the_queue(queue_dir, children, parallelism):
    dir_contents = look_at_the_queue(queue_dir)

    items = children.items()
    if len(items) >= parallelism:
        return None # Already full
    try:
        for fname in dir_contents:
            if fname not in [i[1][0] for i in items]:
                # we're not working on this already, take it
                children[do_fork()] = (fname, time.time())
    except TypeError: # Nothing on the queue, go
        return list()


def look_at_the_queue(queue_dir):
    """Return a sorted list of the queue files"""
    sorted(os.listdir(queue_dir))

def reap_done_children(children):
    try:
        result = os.wait3(os.WNOHANG)
    except OSError as ose:
        return
    if result == (0,0):
        return None
    else:
        pid, status, usage = result
        if status != 0:
            # XXX Pass this on to carbon/statsd/etc.
            print "Pid: {0} failed with an exit code of {1}".format(pid, status)
        # XXX shouldn't be able to get an error here, but just in case
        # it happens in testing... here's a note to self
        del(children[pid])
        print("parent: {0}, child: {1}, user: {2.ru_utime}, sys: {2.ru_stime}, rss_unshared: {2.ru_idrss} ".format(
            os.getpid(), pid, usage ))  # XXX: make these useable metrics


def main():
    """Watch the directory, and send queued files with a configured max
    and a configured timeout per file to be sent.  It looks for
    """
    timeout        = 30     # seconds
    interval       = 1     # seconds
    parallelism    = 10    # number of subprocesses
    sleep_time     = 0.1 # sleep between loops
    dst_host       = "127.0.0.1" # XXX Fixme
    dst_port       = "1111"      # XXX Fixme
    command        = "repr_pickle_sender.py"
    send_queue_dir = "/var/tmp/carbon/send" # XXX FIXME to be an arg/option
    children       = dict() # Dictionary of pid, filename
    graphite_host  = "localhost:2003" # XXX FIXME

    success_count  = 0
    failure_count  = 0

    while True:
        pickup_something_from_the_queue(send_queue_dir, children, parallelism)
        reap_done_children(children) # XXX success/fail count here
        time.sleep(sleep_time)








if __name__ == '__main__':
    main()