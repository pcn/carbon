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
<timeout> is the number of seconds before killing a child process

program must take host, port and the chose file from the queue as
program <host> <port> <file>

The program should write instrumentation info to file descriptor 0
(normally stdin, but not today).

the data should be a string containing the number of metrics, number
of bytes and time taken to transmit, separated by commas.  So for 10
metrics with a total size of 100 bytes to transmit that took 1 second,
the child should call: os.write(0, "10.0,100.0,1.0").

These must never exceed the OS pipe size, I am avoiding doing anything
fancy like pipe deadlock detection by assuming that we'll never have
more than a handful of bytes.

The child can write to fd 0 and exit - the data will be in the pipe,
and the parent can reap and read the data from the read size after
wait3() reaps the child based on my testing.

"""


import sys
import os
import os.path
import signal
import optparse
import time
import resource
import socket
from os.path import dirname, join, abspath

# Figure out where we're installed
BIN_DIR = dirname(abspath(__file__))
ROOT_DIR = dirname(BIN_DIR)

# Make sure that carbon's 'lib' dir is in the $PYTHONPATH if we're running from
# source.
LIB_DIR = join(ROOT_DIR, 'lib')
sys.path.insert(0, LIB_DIR)

from carbon.conf import settings
from carbon import log # XXX: use the log.relay instead of print/sys.stdout.write

HOSTNAME = socket.gethostname().replace('.','_')

def do_fork(command, dst_host, dst_port, filename, write_pipe):
    """Don't wait here, but wire write_pipe to stdin so that
    instrumentation data can be read"""
    pid = os.fork();
    if pid == 0: # child
        # sys.stdout.write("Going to run command: {0} with args {1}\n".format(command,[command, dst_host, dst_port, filename] ))
        # sys.stdout.flush()
        sys.stdin.close()
        os.dup2(write_pipe, 0) # Children can now write to stdin, and we'll os.read() it
        os.execvp(command, [command, dst_host, dst_port, filename])
    else:
        os.close(write_pipe)
        return pid

def log_and_kill_overtime_processes(children, timeout):
    now = time.time()
    for child in children.items():
        if child[1][1] + timeout < now:
            os.kill(child[0], signal.SIGKILL)
            sys.stdout.write("Killed pid {0} (sending {1}): timeout of {2}, was {3} seconds old\n".format(
                child[0], child[1][0], timeout, now - child[1][1]))

def get_sorted_queue(queue_dir):
    """Return a sorted list of the queue files"""
    return

def check_dir_contents(queue_dir, children):
    dir_contents = sorted(os.listdir(queue_dir))
    if len(dir_contents) > 0:
        if set(check_dir_contents.prior_dir_contents) != set(dir_contents):
            sys.stdout.write("INFO: queue dir has {0} waiting items and {1} active processes\n".format(len(dir_contents), len(children)))
            sys.stdout.flush()
            check_dir_contents.prior_dir_contents = dir_contents[:]
        return True
    else: # No files to process
        # print "Dir_contents are {0}".format(dir_contents)
        return False
# Static vars for this function.
check_dir_contents.prior_dir_contents = list()

def check_children_status(children):
    if (time.time() - check_children_status.last_status_time) > settings.CARBON_METRIC_INTERVAL:
        sys.stdout.write( "INFO: At {0} children contains: {1}\n".format(time.ctime(), children))
        sys.stdout.flush()
        check_children_status.last_status_time = time.time()
# Static vars for this function.
check_children_status.last_status_time = 0

def parallelism_below_limit(children, max_parallelism):
    if len(children) >= max_parallelism:
        sys.stdout.write("INFO: {0} active children, limit is {1}.\n".format(len(children), max_parallelism))
        sys.stdout.flush()
        return False # Already full
    return True
# Static vars for this function.
parallelism_below_limit.prior_items = 0

def pickup_something_from_the_queue(queue_dir, children, cmd_sans_file):
    """Runs on the first file to be found in the queue dir"""
    for fname in sorted(os.listdir(queue_dir)):
        if fname not in [i[1][0] for i in children.items()]:
            # we're not working on this already, take it
            do_fork_args = cmd_sans_file[:]
            do_fork_args.append("{0}/{1}".format(queue_dir, fname))
            log.relay("{0}\n".format(do_fork_args))
            pipe = os.pipe()
            do_fork_args.append(pipe[1])
            children[do_fork(*do_fork_args)] = (fname, time.time(), pipe[0])
            return True
    return False


def check_and_run_queue(queue_dir, children, parallelism, cmd_sans_file):
    """For each time this function is run, it checks that the
    conditions are OK for a spool file to be run.  If conditions
    are auspicious, then it shall be done.
    """
    check_children_status(children)
    if check_dir_contents(queue_dir, children) is False:
        return False
    if parallelism_below_limit(children, parallelism) is False:
        return False
    return pickup_something_from_the_queue(queue_dir, children, cmd_sans_file)

def run_the_queue(queue_dir, children, parallelism, cmd_sans_file):
    """While there are items left, and while the limit for the number
    of children hasn't been reached, continue to process files.
    """
    while check_and_run_queue(queue_dir, children, parallelism, cmd_sans_file) is True:
    #   print "Found something to do with {0} children".format(children)
        pass
    # else:
    #     print "Found nothing to do with {0} children".format(children)


# XXX have this called from a signal handler, maybe?
def reap_done_child(children, timeout):
    """Each invocation of this will reap a child."""
    if len(children) < 1:
        return None
    log_and_kill_overtime_processes(children, timeout)
    result = os.wait3(os.WNOHANG)
    if result[0] == 0 and result[1] == 0:
        return None
    else:
        pid, status, usage = result
        # sys.stdout.write("DEBUG: pid: {0}, status: {1}, usage: {2}\n".format(pid, status, usage))
        # sys.stdout.flush()
        if status != 0: # XXX instead of kill, we could use term first and try to get instrumentation from the dead process.
            # XXX Log the failure
            sys.stdout.write("Pid: {0} failed with an exit code of {1}\n".format(pid, status))
            sys.stdout.flush()

        read_fd = children[pid][2]
        perf_string = os.read(read_fd, 128)
        os.close(read_fd)
        try:
            del(children[pid])
        except KeyError: # Shouldn't happen, die and get restarted if it does.
            sys.stdout.write("ERROR trying to kill {0}.  Children is: {1}\n".format(pid, children))
            sys.stdout.flush()
            raise
        # sys.stdout.write("DEBUG: parent: {0}, child: {1}, user: {2.ru_utime}, sys: {2.ru_stime}, rss_unshared: {2.ru_idrss}\n".format(
        #     os.getpid(), pid, usage ))  # XXX: make these useable metrics?
        # sys.stdout.flush()
        if perf_string:
            return [float(p) for p in perf_string.split(',')]


def update_all_perf(all_perf, perf):
    """Updates the values in all_perf (in place - caller beware of
    pass-by-reference) by adding values from perf
    """
    for i in range(3):
        all_perf[i] += perf[i]

def reap_done_children(children, timeout):
    """Reaps as many child processes as are ready to be reaped, and
    returns a summary of their total performance.
    """
    all_perf = [0.0, 0.0, 0.0]
    perf = reap_done_child(children, timeout)
    if perf:
        update_all_perf(all_perf, perf)
    while perf:
        perf = reap_done_child(children, timeout)
        if perf:
            update_all_perf(all_perf, perf)
    return all_perf

def send_perf_data(all_perf, dst_host, dst_port):
    """Log and send perf data.  For sending, this will look for the
    UDP port to be enabled in the relay config.
    """
    if all_perf[2] > 0.0:
        sys.stdout.write("INFO: {0} metrics: {1} bytes: {2} time: {3} ({4:.1f} metrics/sec, {5:.1f} bytes/sec)\n".format(
            os.path.basename(sys.argv[0]), all_perf[0], all_perf[1], all_perf[2],
            all_perf[0]/all_perf[2], all_perf[1]/all_perf[2]))
    else:
        sys.stdout.write("INFO: {0} metrics: {1} bytes: {2} time: {3} (0.0 metrics/sec, 0.0  bytes/sec)\n".format(
            os.path.basename(sys.argv[0]), all_perf[0], all_perf[1], all_perf[2]))
    sys.stdout.flush()
    # Hopefully the relay is up and running via udp
    if settings.ENABLE_UDP_LISTENER is True:
        host = settings.UDP_RECEIVER_INTERFACE
        port = settings.UDP_RECEIVER_PORT
        if settings.instance is None: # XXX Does paying attention to the instance make any sense here?
            fullMetric_prefix = '{0}.relays.{1}.queue-runner.{2}-{3}'.format(settings.CARBON_METRIC_PREFIX, HOSTNAME, dst_host, dst_port)
        else:
            fullMetric_prefix = '{0}.relays.{1}-{2}.queue-runner.{3}-{4}'.format(settings.CARBON_METRIC_PREFIX, HOSTNAME, settings.instance, dst_host, dst_port)
        sock = socket.socket(socket.AF_INET, # Internet
                             socket.SOCK_DGRAM) # UDP
        for i, metric_name in ((0, "metric_count"), (1, "bytes_count"), (2, "time")):
            message = "{0}.{1} {2} {3}\n".format(fullMetric_prefix, metric_name, all_perf[i], time.time())
            sock.sendto(MESSAGE, (UDP_IP, UDP_PORT))

def main():
    """Watch the directory, and send queued files with a configured max
    and a configured timeout per file to be sent.
    """
    sleep_time             = 0.5 # sleep between loops
    children               = dict() # Dictionary of pid, filename
    all_perf               = [0.0, 0.0, 0.0]
    prior_metric_dump_time = time.time()
    metric_dump_interval   = settings.CARBON_METRIC_INTERVAL # seconds XXX get from carbon.conf


    # XXX add a config option for the address of the relay to send
    # instrumentation data to.
    success_count  = 0
    failure_count  = 0

    if len(sys.argv) < 4:
        """usage: queue-runner.py <program> <host> <port> <spool dir>
<program> is the program that will read files from the spool directory
<host> is the host to get passed to <program>
<port> is the port it will send to
<spool dir> is the directory to read files from which will be sent.
<parallelism> is the number of sending processes to allow
<timeout> is the number of seconds before killing a child process

program must take host, port and the chose file from the queue as
program <host> <port> <file>
"""
    command = sys.argv[1]
    dst_host = sys.argv[2]
    dst_port = sys.argv[3]
    send_queue_dir = sys.argv[4]
    parallelism = int(sys.argv[5])
    timeout = int(sys.argv[6])
    pipe = os.pipe()

    status = "{0} starting with queue at {1} and destination of {2}:{3} and command {4} with a timeout of {5}\n"
    sys.stdout.write(status.format(sys.argv[0], send_queue_dir, dst_host, dst_port, command, timeout))
    sys.stdout.flush()

    cmd_sans_file = [command, dst_host, dst_port]
    while True:
        run_the_queue(send_queue_dir, children, parallelism, cmd_sans_file)
        perf = reap_done_children(children, timeout) # XXX success/fail count here
        update_all_perf(all_perf, perf)
        if (prior_metric_dump_time + metric_dump_interval) < time.time():
            send_perf_data(all_perf, dst_host, dst_port)
            prior_metric_dump_time = time.time()
            all_perf = [0.0, 0.0, 0.0]
        sys.stdout.flush()
        time.sleep(sleep_time)


if __name__ == '__main__':
    main()