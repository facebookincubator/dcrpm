# History
Late in 2013, a problem became clear: we were having a lot of issues with RPMs and the RPM databases on our CentOS machines. A series of tools was created to help deal with this in an automated fashion.

dcrpm was created to specifically address the problems coming from the lower levels of the RPM database (`db4`). It tries to do a `rpm -qa` and makes sure it gets back a reasonable response in a generous amount of time.

If the subprocess fails to complete in that interval or returns too few packages, it will run `db_recover` in `/var/lib/rpm` to attempt to clean up the mess. Then it looks for processes which had the old `/var/lib/rpm/__db.001` open and kills them, as they will never manage to "wake up" from the sort of infinite loop which can happen when db4 is truly broken.

As of mid-April 2014, dcrpm also checks for mismatches between RPM tables.  Believe it or not, it's possible to see packages in `rpm -qa` which will fail when you run `rpm -q <package>`.  It uses a nasty little shell pipeline to look for such anomalies and then uses RPM to rebuild its own tables if necessary.

In late April 2014, dcrpm picked up the notion of verifying individual tables.  It will run `db_verify` on the tables in `/var/lib/rpm` (those starting with a capital letter), and if any anomalies are found, will run a RPM rebuild.  October 2014 added a feature to clean up outstanding yum transactions and also deal with subprocess timeouts gracefully (a bug fix).

The original dcrpm was an internal C++ implementation by [Rachel Kroll](mailto:rkroll@fb.com). It was rewritten Python in 2017 by [Sean Karlage](mailto:skarlage@fb.com) to remove Facebook internal dependencies and make it able to run on OSX as well. This new implementation is the starting point of this codebase.
