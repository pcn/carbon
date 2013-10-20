What is the carbon-cache?
=========================

Caching is a goal in graphite - both the web frontend and the carbon
transport layer.

Currently there are two caches you can use in the graphite stream of
data between (source -> graph in your browser). One is the
carbon-cache, and the other is memcached.  If you want to know more
about these, you can start with
http://www.aosabook.org/en/graphite.html.

The one I want to talk about the most is the carbon-cache.  My
thoughts here are based on the following observations in how graphite
is used in our organization, and in others:

1) The fundamental unit of graphite is the metric. However, the
   most-used unit of graphite is a dashbaord which combines multiple
   metrics and presents multiple charts at the same time.

1a) Dashbaords are often "abused".  I put "abuse" in quotes because it
    really means that the size of dashbaords will cause graphite to
    behave poorly.  The mechanism for this is usually done by using a
    single dashboard among many users, and that dashboard may have one
    or more of the following properties: many (many many!) metrics
    need to be queried to render the dashbaord; the dashboards update
    constantly (e.g. every minute, every 30 seconds, every 10 seconds
    in hopes of getting the newest data); only a small subset of the
    graphs are actually used, but there is resistence to separating
    them out; lots of calculations are done on a lot of metrics.

    The last one is much harder to fix, the others may be fixable.

2) Dashboards are highly cacheable, but the carbon cache doesn't
   really optimize for the "dashboard" use case, instead it optimizes
   for the "what if someone wants to query a couple of data points for
   a metric that no-one normally queries, and do it quickly?"

So my thought is, why don't we optimize for the common case in a way
that doesn't penalize the occasional case too badly?


carbon-cache: maybe no longer the right cache?
==============================================

The carbon cache is an interesting combination of features.  It is:

* A receiver of metrics from the network.

* A writer of metrics to disk

* A broad, shallow cache of recent metrics.

* A queue for when the disk is slow - it buffers metrics when too many
  come in and operations such as creates start to slow down, and thus
  the linear processing of the cache slows down everything that it's
  doing.

The problem that I have observed is that the caching function becomes
a bottleneck.  The cache process becomes overwhelmed by storing and
aging out datapoints, while at the same time trying to commit data
points to disk and write them efficiently.  I believe that teasing
these duties apart is essential for graphite to scale.

I think the way to do that is to use some of the modern cache
technologies to enable experiments with scalable caches by making the
carbon-cache a more transparent layer with a better set of interfaces.


What could be different?
========================

I think there's a fundamental observation based on how graphite is
used now.  It's become used as a web resource, and so in one
particular dimension, it's "web-scale": it ingests many, many metrics
that will never, ever, be queried.  My roug guess is that 90%+ of all
metrics in our clusters are never looked at, 9% are viewed a few times
a day, and 1% are viewed constantly.

This distribution of query patterns calls for a cache that caches
fewer data points, and caches deeply - specifically only caching
metrics that are being used, and storing all of the data points for
that metric within the timeframes that are being observed (e.g. per a
dashboard that is shared across a team)

However, the current cache caches broadly, holding all metrics, and in
a shallow manner, only storing a certain number of metrics overall,
which means that it rarely provides a significant speedup to any query.

Here's a thought on how I think we can fix that:

1) An incoming metric enters a carbon-writer service which cannot be
   use as a cache it'll just write to disk and minimize its processing
   and memory needs (that is, it'll queue until all metrics are
   flushed to disk, but never provide and support a query interface).
   The goal of the writer is to get to stable storage ASAP.  In
   addition, the writer should be able to delete metrics.

2) Queries for metrics need to be provided from a carbon-reader
   service.  This will connect to any configured backend and read data
   from disk (rrd, whisper, ceres, etc).  This will be slower than the
   current path from webui -> disk.  However, it does network-enable
   the protocol which will enable horizontal scaling of the webui
   without needing e.g. nfs.  Also, we will need optimization to make
   this process faster for the front-end/user.  That's next.

3) Imagine that instead of querying from the carbon-reader, the same
   series of metrics that the writer gets will be sent to a
   read-through cache process that only caches.

   It receives data, filters out and discards data that it doesn't
   need (meaning no queries have been made for that data), and caches
   the data that it does need (meaning metric names where queries have
   been made for it).  If it doesn't have that data in-cache, it will
   go to the reader process to fetch that data, then cache it.

   This means that the cache process only has to manage memory for
   itself, and doesn't block on disk writes, and it reads a lot less.

3a) Its function will be to satisfy queries from the web front-end,
    and to save the ranges that were queried for.  When a range is
    queried, all of the results will be saved to memory.  When memory
    is full enough, or when a particular metric hasn't been queried in
    long enough, that metric will be flushed.

3b) There's an opportunity to do a lot of dynamic caching.  When data
    for a relative time frame is queried, the cache can know that the
    oldest data can be removed, so it will remove data older than
    e.g. 2 hours for a query that is for data that is from "now" until
    "now - 2 hours".  So the cache may be able to make intelligent
    choices like "I have had 500 queries for a 1 hour timeframe, but
    only 1 query for a 2 month timeframe.  It's less important, and I
    will evict 1 month, 30 days, and 22 hours worth of data much
    sooner than I will the 2 last two hours".  This stuff is hard, but
    hopefully the hueristics/models for this will be useful
    immediately with some basic heuristics and more complex decisions
    can be customized per dashboard.

4) The web front-end will have all knowledge of storage formats
   removed from it.  It will not directly access any data from disk,
   only from the cache.  This should make the webui a lot slimer and
   easier to reason about.  It also makes it more focused on
   presenting data and it makes it easier to separate it from the
   source of the data.

5) For the optimal webui experience, cache clusters could be made to
   hold the content of a dashboard in cache.  All updates to that
   dashboard would be directed to the cache's receiver.

6) The cache mechanism itself may not be best implemented in python -
   it may be that the best way to do this is as an optimized cache
   such as memcached, hazelcast, redis. etc. where more memory is
   available, where sharding may happen "magically", etc. with just a
   controlling front end that accepts requests, and the
   implementations are left up to the particular business that is
   using it.  The important thing is that a well-behaved
   implementation is provided that can be used out of the box.

7) While I'm at it, there should be a carbon-metric-manager.  That
   would provide a small and probably growing set of features.  The
   main things I can see being hugely desireable for graphite are:
   deleting metrics and copying datapoints (e.g. from one node in a
   consistent-hashing system to another, or just from one hierarchy to
   another).

I intend to start experimenting with this soon. It seems that this is
going to be a very disruptive change, so I think it'll be necessary
for me to fork carbon and graphite web for a while in order to be able
to not confuse people as to what is going on.

I think this is not entirely orthogonal to what @dieterbe is working
on, but I do hope that if this works well enough that it can be rolled
back into graphite to make the common use cases faster, better, etc.
