#!/usr/bin/env python

"""This will generate files that can be parsed by python,
and which a fast queue runner can pickle and send, fast.

Usage:
directly_flood_cache_with_random_crap.py <queue_dir> <count_per_line> <files_to_write> <perm_string> <perm_string_len>

The arguments are:

<queue dir>: the directory where files will be deposited
<count_per_line>: the number of tuples to include on the same line
<files_to_write>: the number of files taht'll be created
<perm_string>: The string that will be permutated to get strings to send
<perm_string_len>: the number of characters to be used to create unique strings from perm_string

An example:

/opt/graphite/bin/directly_flood_cache_with_random_crap.py /var/tmp/pn 500 300 15 abcdefghijklmnop 6

creates

(graphite)vagrant@vagrant-ubuntu-precise-64:/vagrant/carbon$ ls -laFsh /var/tmp/pn/
total 123M
4.0K drwxrwxr-x 2 vagrant vagrant 4.0K Jun 20 04:35 ./
4.0K drwxrwxrwt 4 root    root    4.0K Jun 20 04:04 ../
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.0.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.10.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.11.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.12.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.13.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.14.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.1.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.2.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.3.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.4.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.5.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.6.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.7.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.8.output
8.2M -rw-rw-r-- 1 vagrant vagrant 8.2M Jun 20 04:39 pn_test.prefix.9.output

The values and timestamp will the the current time as of the start of the test.

A line can't greater than 2^32 bytes, so hold off on the ridiculous values.

"""

import sys
import os
import itertools
import time
import cPickle as pickle


def main():
    queue_dir = sys.argv[1]
    count_per_line = int(sys.argv[2])
    lines_per_file = int(sys.argv[3])
    files_to_write = int(sys.argv[4])
    perm_string = sys.argv[5] # abcde will give us 600 permutations for stats
    perm_string_len = int(sys.argv[6])
    stat_iterator = ("".join(l) for l in itertools.permutations(perm_string, perm_string_len))
    write_stats_like_a_mofo(queue_dir, count_per_line, lines_per_file,
        files_to_write, stat_iterator)

def write_stats_like_a_mofo(q_dir, per_line, per_file, f_count, stat_iterator):
    line_list = list()
    t         = time.time()
    start     = 0
    end       = start + per_line
    print "f_count is {0}".format(f_count)
    for count in range(f_count):
        f_name = "{0}/pn_test.prefix.{1}.output".format(q_dir, count)
        print "File count is {0}".format(count)
        f = open(f_name, 'w')
        try:
            for iteration in range(per_file):
                # print "Iteration start index: {0}, end index: {1}".format(start, end)
                line_list = [("test.{0}".format(stat_iterator.next()), (t, t)) for l in range(per_line) ]
                f.write(repr(line_list))
                f.write("\n")
        except StopIteration:
            # Don't bother with the last line, it's more trouble than it's worth.
            print "Closing {0}".format(f_name)
            f.close()
            return
        print "Closing f_name"
        f.close()

if __name__ == '__main__':
    main()
    time.sleep(1)