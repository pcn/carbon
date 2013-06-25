#!/usr/bin/env python

usage = """Makes the directory+files necessary for a particular
remote for the spooling relay to be setup.

Performs setup with runit.

Needs:
remote_host - the host this will send to
remote_port - the port this will connect to
spool_path  - the directory that will contain the send and temp queues
runit_dir   - The directory that runit will create files in
log_dir     - the directory where a log directory will be created for runit
owner       - the user to run as
group       - the group to run as
parallelism - the max number of subprocesses to use when sending (10 recommended)
timeout     - the timeout before a sending process should be killed

Example:

sudo setup_runit_spooling_sender.py \
    ec2-54-235-34-178.compute-1.amazonaws.com \
    2004 \
    /var/spool/carbon \
    /etc/sv \
    /var/log \
    www-data \
    www-data \
    10 \
    120

Output:
/var/spool/carbon/temp/ec2-54-235-34-178.compute-1.amazonaws.com:2004
/var/spool/carbon/send/ec2-54-235-34-178.compute-1.amazonaws.com:2004
/var/log/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004
/etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004
/etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004/supervise
/etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004/log
/etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004/log/supervise
/etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004/run created and set executable
/etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004/log/run created and set executable

To start this service, symlink /etc/sv/carbon-sender-ec2-54-235-34-178.compute-1.amazonaws.com:2004 into /etc/service (on debian/ubuntu)

"""

import sys
import os
import stat
import errno
import pwd


def mkdir_p(path, owner=None, group=None, perms=None, verbose=True):
    default_dir_perms = stat.S_IWUSR|stat.S_IXUSR|stat.S_IRUSR|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
    if owner:
        os.chown(path, pwd.getpwnam(owner).pw_uid, pwd.getpwnam(owner).pw_gid)
    if perms:
        perms = perms
    else:
        perms = default_dir_perms
    os.chmod(path, perms)
    if verbose:
        print(path)


def make_spool_dirs(spool_path, dirname, owner):
    """SPOOLING_DIR/temp and SPOOLING_DIR/send are created. These must match what's in carbon.conf's SPOOLING_DIR """
    mkdir_p("{0}/temp/{1}".format(spool_path, dirname), owner=owner)
    mkdir_p("{0}/send/{1}".format(spool_path, dirname), owner=owner)

def make_log_dir(log_dir, dirname, owner):
    """The log dir will be named LOG_DIR/carbon-sender-HOST:PORT"""
    mkdir_p("{0}/carbon-sender-{1}".format(log_dir, dirname), owner=owner)

def make_runit_dir(runit_dir, dirname, owner, runit_run, runit_log_run):
    """The runit service dir will be named PREFIX/carbon-sender-HOST:PORT"""
    file_exec_perms = stat.S_IWUSR|stat.S_IXUSR|stat.S_IRUSR|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH|stat.S_IXOTH
    _dir = "{0}/carbon-sender-{1}".format(runit_dir, dirname)
    mkdir_p(_dir, owner=owner)
    mkdir_p("{0}/supervise".format(_dir), owner=owner)
    mkdir_p("{0}/log".format(_dir), owner=owner)
    mkdir_p("{0}/log/supervise".format(_dir), owner=owner)
    with open("{0}/run".format(_dir), 'w') as f:
        f.write(runit_run)
    os.chmod("{0}/run".format(_dir), file_exec_perms)
    print("{0}/run created and set executable".format(_dir))
    with open("{0}/log/run".format(_dir), 'w') as f:
        f.write(runit_log_run)
    os.chmod("{0}/log/run".format(_dir), file_exec_perms)
    print("{0}/log/run created and set executable".format(_dir))


def main(argv=sys.argv[:]):
    if len(argv) < 9:
        print(usage)
        sys.exit(2)
    hostandport = "{0}:{1}".format(argv[1], argv[2])
    spool_path  = argv[3]
    runit_dir   = argv[4]
    log_dir     = argv[5]
    owner       = sys.argv[6]
    group       = sys.argv[7]
    parallelism = sys.argv[8]
    timeout     = sys.argv[9]
    make_spool_dirs(spool_path, hostandport, owner)
    make_log_dir(log_dir, hostandport, "root")
    runit_run = """#!/bin/sh
. /opt/graphite/bin/activate
exec 2>&1
exec chpst -u {0}:{1} -- \
    /opt/graphite/bin/queue-runner.py \
    repr-pickle-sender.py \
    {2} \
    {3} \
    {4}/send/{5} \
    {6} \
    {7}""".format(owner, group, argv[1], argv[2], spool_path, hostandport, parallelism, timeout)
    runit_log_run = """#!/bin/sh
exec svlogd -ttt {0}/carbon-sender-{1}
    """.format(log_dir, hostandport)
    make_runit_dir(runit_dir, hostandport, "root", runit_run, runit_log_run)

    print "\nTo start this service, symlink {0}/carbon-sender-{1} into /etc/service (on debian/ubuntu)\n".format(runit_dir, hostandport)

if __name__ == '__main__':
    main()