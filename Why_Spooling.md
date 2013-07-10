What is graphite?
=================

At monitorama 2013, talking with @mlienart, it was mentioned that what
graphite is, is a bit of an open question.

My understanding since then is that graphite is really 3 things:

* A very simple client that can accept metrics via a simple tcp or udp
  connection.

* One or more transport system that can take metrics, and shuttle them
  around, including some transformations in-flight (e.g. the
  aggregation service(s)), some filtering (e.g. the rules-based
  router), and some replication (e.g. the consistent hashing router).

* It's a web front-end that takes the stored metrics and allows, via a
  url-based API, for the query and display of the metrics as graphs.

* Lastly, graphite is commonly associated with the whisper file
  format, which is a format that improves on the rrd format in that it
  allows for backfilling (which rrd has subsequently added).  That
  format is now being de-emphasized in favor of a new format, called
  "ceres" (pronounced "series").

Graphite, then is all of these components tied together into a
relatively simple to use, simple to install, and transparent system.

What problems have we had?
==========================

Graphite is a great tool.  My understanding of it has grown greatly
this year, and I've been using it for almost 2 years.

The biggest problem we've had is that the relay code that graphite
includes has multiple layers of queueing.  There is a queue internal
to the relay code which was inefficient.  The core of the problem was
seen as being two-fold:

1. The code in 0.9.10 and prior was using a regular python list as its
main queue, and regularly adding to it, then removing one graph, and
copying the remainder of the list to another list.  This is very
inefficient in python.

2. The path for metrics was defaulting to sending a metric as soon as
it was received.  This prevented there being any benefit from batching
writes.

The impact of these two issues combined were severe.  In trying to
send to a remote site when queueing about 10k metrics, we could recover.

However, once we reached approx. 50k metrics queued, it was unlikely
that the relay could resume - that's right, it appeared to just get
stuck at that point.

What's more the following lesser issues were apparent

1. There was no instrumentation enabled in the relay

2. The instrumentation that was disabled ended up making no sense when I re-enabled it.

The first iteration
===================

The first fix can be found at https://github.com/graphite-project/carbon/pull/92

This addresses the big and small issues by using a deque and by
batching up writes.  This tremendously improved relay performance.
Using this we could relay the load we needed to - about 70k
metrics/minute, and we could tolerate and clear queues that built up
when the relay suffered connection issues (mostly - but some special
issues, like the internet being broken, still required a re-start).

The second iteration, or progress crushed by more progress
==========================================================

So everything was working for about a minute, and then suddently we've
exceeded the 70k number, and we're pushing 100k, 150k, 200k, etc.
We've more than doubled our metric count, and suddenly new issues
opened up.

The biggest issue was this:

There was a hidden queue.

The write path from this:

  https://github.com/graphite-project/carbon/blob/master/lib/carbon/client.py#L57

didn't actually write directly to the network.  Instead it writes here:

  https://github.com/twisted/twisted/blob/trunk/twisted/internet/abstract.py#L229

What you'll notice is that all writes end up being turned into a
string.  The string then gets managed, and until the string gets below
a certian length, the list behind the string keeps getting larger as
the string gets processed.

My undersatanding, my mental model of this, is that once this starts,
and the list gets large, each subsequent clearing of the list ->
string takes longer because the contents of the string must be below a
very small number of kB before the list is again turned into the list.
When it's over some magic number (based on the CPU power and latencies
to the relay, and the number of destinations this relay delivers to)
the amount of time it takes to send the string will be enough that the
list that has built up will always create a string that is too large
to clear before the next array clearning.  The array will continue to
grow to a huge size, and as more data comes in, this situation gets
worse and worse and cannot recover.

Darn.

So what to do about it?

The next iteration is spooling to disk and have independent workers
clear out a queue.


Why Spooling?
=============

The thing about graphite that I've encountered is that as the internet
has grown, and especially as cloud-based usage of graphite has grown,
there are weaknesses that didn't exist prior that are now glaring
problems.

The relay is a simple bit of code that allows for multiple
personalities, in order to do some very interesting slicing and
dicing.

The relay is built on top of the twisted infrastructure, and twisted
provides ways to work around the queues we discovered.  However, my
feeling is that that will present a few other scalability issues.

My thoughts are:

1. Twisted provides a mechanism of avoiding this write path, and
   signaling that writes need to block.  We could change the framework
   to do this, right?

   Probably. But since just reading a string and then reading another
   list is taking a long long time, it suggests that there may be some
   inherent scalability limit that we're going to keep running into if
   we go down that path.  The main issue here is the Cpython
   single-processor limit.

2. Make a simpler, non-twisted relay - maybe with less code, there
   will be less work, and better performance?

   Maybe, but without an async style of development, we have to resort
   to threads.  Threads are OK, and may also have worked, but that
   would require a complete re-write.  It may have resulted in a
   fairly simple server, but I'm not looking for a complete re-write.

So, one way of increasing performance with an inherently single-cpu
runtime like cpython is to parallelize the work.  Since the problems
we're having are exhibited and aggrevated by having remote
destinations 100ms away, and having multiple destinations, it seems
like parallelizing to mulitple processes would benefit greatly by
spooling to disk.

Spooling to disk and then having separate runners solves this problem
by allowing for decoupling.  The relay can run far faster since all it
will do at this point is write to a file, then present this file into
the outbound queue.  The queue runners can run their queue.  In
principle, the relay can now just relay to disk - even if one of the
destinations is down, the metrics can just be written to disk, to be
delivered when that destination is back.  No in-memory queueing.
