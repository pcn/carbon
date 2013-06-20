#!/usr/bin/env python

"""Runs through a queue of graphite-style carbon metrics and
send them.

It does this by picking up files in the send queue directory, and
sending them to the configured endpoint (the dest_host and dest_port
arguments).

usage: queue-runner.py <program> <host> <port> <spool dir>

<program> is the program that will read files from the spool directory
<host> is the host to get passed to <program>
<port> is the port it will send to
<spool dir> is the directory to read files from which will be sent.

program must take host, port and the chose file from the queue as
program <host> <port> <file>
"""


import sys
import os
import os.path
import optparse
import time
import resource

def do_fork(command, dst_host, dst_port, filename):
    """Don't wait here, wait and reap children in main()"""
    pid = os.fork();
    if pid == 0: # child
        sys.stdout.write("Going to run command: {0} with args {1}\n".format(command,[command, dst_host, dst_port, filename] ))
        sys.stdout.flush()
        os.execvp(command, [command, dst_host, dst_port, filename])
    else:
        return pid

def log_overtime_processes(children):
    now = time.time()
    for p in children.items():
        if p[1][0] > now:
            pass # XXX: to do : log that the process is overtime.
            # And kill it and put the file back on the queue, implicitly.

def look_at_the_queue(queue_dir):
    """Return a sorted list of the queue files"""
    return sorted(os.listdir(queue_dir))

def pickup_something_from_the_queue(queue_dir, children, parallelism, cmd_sans_file):
    dir_contents = look_at_the_queue(queue_dir)
    if len(dir_contents) > 0:
        if set(pickup_something_from_the_queue.prior_dir_contents) != set(dir_contents):
            sys.stdout.write("dir_contents: {0}\n".format(dir_contents))
            sys.stdout.write("prior_dir_contents: {0}\n".format(pickup_something_from_the_queue.prior_dir_contents))
            sys.stdout.flush()
            pickup_something_from_the_queue.prior_dir_contents = dir_contents[:]
    items = children.items()
    if len(items) >= parallelism:
        sys.stdout.write("There are more children than the parallelism limit allows. Pass\n")
        sys.stdout.flush()
        # XXX implement a kill function on transactions more than the timeout
        return None # Already full
    try:
        for fname in dir_contents:
            # sys.stdout.write("Maybe {0}\n".format(fname))
            # sys.stdout.flush()
            if fname not in [i[1][0] for i in items]:
                # we're not working on this already, take it
                sys.stdout.write("Going to work on {0}\n".format(fname))
                sys.stdout.flush()
                cmd = [cmd_sans_file[0], cmd_sans_file[1], cmd_sans_file[2]]
                cmd.append("{0}/{1}".format(queue_dir, fname))
                sys.stdout.write("{0}\n".format(cmd))
                children[do_fork(*cmd)] = (fname, time.time())
    except TypeError: # Nothing on the queue, go
        raise
        # print "Emtpy queue"
        # return list()

pickup_something_from_the_queue.prior_dir_contents = list()


def reap_done_children(children):
    if len(children) < 1:
        return None
    result = os.wait3(os.WNOHANG)
    if result[0] == 0 and result[1] == 0:
        return None
    else:
        pid, status, usage = result
        sys.stdout.write("pid: {0}, status: {1}, usage: {2}\n".format(pid, status, usage))
        sys.stdout.flush()
        if status != 0:
            # XXX Pass this on to carbon/statsd/etc.
            sys.stdout.write("Pid: {0} failed with an exit code of {1}\n".format(pid, status))
            sys.stdout.flush()
        # XXX shouldn't be able to get an error here, but just in case
        # it happens in testing... here's a note to self
        try:
            del(children[pid])
        except KeyError:
            sys.stdout.write(children)
            sys.stdout.flush()
            raise
        sys.stdout.write("parent: {0}, child: {1}, user: {2.ru_utime}, sys: {2.ru_stime}, rss_unshared: {2.ru_idrss}\n".format(
            os.getpid(), pid, usage ))  # XXX: make these useable metrics
        sys.stdout.flush()


def main():
    """Watch the directory, and send queued files with a configured max
    and a configured timeout per file to be sent.  It looks for
    """
    timeout        = 30     # seconds
    interval       = 1     # seconds
    parallelism    = 10    # number of subprocesses
    sleep_time     = 0.1 # sleep between loops
    command        = "repr_pickle_sender.py"
    dst_host       = "127.0.0.1" # XXX Fixme
    dst_port       = "1111"      # XXX Fixme
    send_queue_dir = "/var/tmp/carbon/send" # XXX FIXME to be an arg/option
    children       = dict() # Dictionary of pid, filename

    success_count  = 0
    failure_count  = 0

    if len(sys.argv) < 4:
        """usage: queue-runner.py <program> <host> <port> <spool dir>

<program> is the program that will read files from the spool directory
<host> is the host to get passed to <program>
<port> is the port it will send to
<spool dir> is the directory to read files from which will be sent.

program must take host, port and the chose file from the queue as
program <host> <port> <file>
"""
    command = sys.argv[1]
    dst_host = sys.argv[2]
    dst_port = sys.argv[3]
    send_queue_dir = sys.argv[4]

    sys.stdout.write("{0} starting with queue at {1} and destination of {2}:{3} and command {4}\n".format(sys.argv[0], send_queue_dir, dst_host, dst_port, command))
    sys.stdout.flush()

    cmd_sans_file = [command, dst_host, dst_port]
    while True:
        pickup_something_from_the_queue(send_queue_dir, children, parallelism, cmd_sans_file)
        reap_done_children(children) # XXX success/fail count here
        time.sleep(sleep_time)


if __name__ == '__main__':
    main()