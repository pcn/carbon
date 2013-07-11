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
main queue, and regularly adding one metric to it, then removing one
metric, and copying the remainder of the list to another list.  This
is very inefficient in python.

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

Some other advantages
=====================

There is a complexity cost in implementing carbon-compatible processes
in other languages.  The combination of the twisted format that's
being used to send over the wire, and the use of the python pickle
format means that using the current relay pretty much ties all
interaction with carbon to using tools implemented in python.

Why?  Well, even though a metric can come in via the pickle protocol
(binary serialized format) or via the line protocol (line-oriented
text protocol), once that metric hits the relay, there is currently
only support for ferrying the metric along via the binary pickle
format via tcp.  That's not codified or required by the receiving
side.  It's because the only sending code that's implemented is the
binary pickle sender.

By de-coupling via spooling, the spool can be written to in some
format, but sent in another format.

Some ideas that could take advantage of this:

* Send to riemann using the line protocol.  This would allow analysis
  of data in the carbon stream by riemann without having to implement
  the python pickle protocol in clojure (not impossible, but not
  necesarily the best use of one's time)

* Write to a separate data store (e.g. opentsdb, kairosdb, etc)

* Experiment with other serialization protocols to judge the impact
  of changes.

* Make it easier to test by writing test loads to a spool, and watching
  the performance of the relay and caches under artificial loads.

* If the load characteristics change, a single spool can be stopped,
  and the parallelism can be changed in order to decrease or increase
  the rate at which metrics catch-up.

* micro-aggregators: if some computation is very heavy-weight, then it
  can be turned into a micro-aggregator.  Instead of the default
  sender, the micro-aggregator can read the spool, and every period
  (some number of seconds defined by the aggregator in question) it
  can perform an arbitrary agrregation function, and feed the results
  back into the relay.  The rules-based relay can be used to forward
  only the relevant metrics to the micro-aggregation destination
  (which could be local or remote) and the function(s) necessary could
  be run, data preserved for the desired time - basically anything
  could be done, and the results forwarded on as a "business policy"
  defined outside of the main purpose of the carbon metrics relay
  functionality.

Issues
======

There are some things that I'd like to do better.

* Currently the # of metrics that a sender is sending is only reported
  at the end of a run.  So if you have a million metrics that are sent
  over 5 minutes via 1 process, the queue-runner will only report that
  at the end of 5 minutes (it will, however, report both the time
  taken and the number of stats so the correct rate will be reported,
  but it would appear that far fewer metrics were sent than actually
  were because the rate of 200,000/minute over that 5 minutes will be
  reported for 1 minute only, not over 5 minutes).  It should be
  possible to have the sender report metrics every few seconds and
  have the queue-runner read and report that via select()ing or
  poll()ing on the pipe communicating with the child, in order to
  provide better intrumentation.

* I'm eval()ing python repr() output of the lists that the relay
  creates internally.  I feel like ths should be safe, but I'm not
  entirely comfortable with this.  Aside from something like json,
  which has greater parsing overhead than python reprs, I'm not sure
  if there is a better (fast, language-neutral, human-readable) format
  for spooling data.  Some advantages of the repr format is that it is
  line-oriented the way I'm using it, an that implicitly allows the
  relay to control the batch size of all of the senders.  This may not
  be a great idea, either - it may be better to make each sender
  configurable.  If that implicit configuration isn't that important,
  it may be better to just use the carbon line format instead?

  In addition, the use of eval() in the sender does mean that if the
  spool is not secured, the sender can be asked to do truly horrible
  things.  This isn't news to an experienced python developer, or to
  an experienced sysadmin, but graphite is great because it has a low
  barrier to entry, and this sort of "oops" is easy to make if it's
  done by someone who doesn't understand why it's important.

* Currently, "nc" (netcat) is used to actually communicate with the
  network.  This is a huge time-saver - it means no network
  programming!  And network programming is very easy, and very easy to
  do wrong.  I expect that in the final form the default repr sender
  will open its own socket and write to it, etc. and that'll all be
  fine, but for now nc is what's doing the heavy lifting there.
