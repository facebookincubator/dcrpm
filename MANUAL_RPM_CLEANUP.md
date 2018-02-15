# Tips on cleaning up broken RPM databases by hand

This document is compendium of tips and tricks to troubleshoot and (hopefully) remediate issues around RPM and Yum. It was originally written with CentOS 5 in mind, and has been updated throughout the years to catalog new issues that came up; keep in mind that not everything here will necessarily apply to the lastest versions of CentOS or RHEL. Most of this logic is automated in these days `dcrpm`, which tries hard to keep the low-level Berkeley DB files in `/var/lib/rpm` clean, and that should be your first stop to try and fix things.

However, we have other ways for the RPM database to get messed up. If something hits RPM or Yum with `kill -9` while it's in a _critical section_ in terms of updates, you may wind up with unfinished transactions. This can also happen if the machine is ungracefully rebooted, e.g. by pulling the plug on it.

Some problems affect the whole database, but others only affect one or two packages.  In other words, if your RPM db has 1000 packages in it, and just one of them is messed up, things may be entirely good up until you get to that one. Then it'll bomb.

## What's broken?
The key thing to run here is this one command:
```
package-cleanup --problems
```
You'll run that a lot in the course of working on this stuff.

## Missing tuples
yum might see this if you're missing certain packages, or pieces of them:
```
Error: Package tuple ('foo', 'x86_64', '0', '1.0.0', '1403171058') could not be found in rpmdb
```
In this case, follow along with "Missing dependencies for existing packages". Odds are, step #1 (`package-cleanup | ... | ... | ... xargs yum reinstall -y`) will clean it up for you.

## Duplicate packages
Sometimes due to yum being killed at the wrong time you can end up with duplicate packages. To see what duplicate packages you have run:
```
package-cleanup --dupes
```
If it's a simple package install that went awry you can often fix this with:
```
package-cleanup --cleandupes
```
This will roll "forward" - it will attempt to finish what was started by removing the older package. However, if an OS upgrade is what got nuked, then you have to roll backwards instead (a long list of dupes - more than 5 or so - is most likely this case). If that's the case you want to remove the newest. We have [patched](https://github.com/rpm-software-management/yum-utils/pull/5) `package-cleanup` to support that, but it may not be rolled out yet in your distribution. To try it out:
```
package-cleanup --cleandupes --removenewestdupes
```

## rpmdbNextIterator
If you see this error:
```
error: rpmdbNextIterator: skipping h#      60 Header V3 DSA signature: BAD, key ID 6b8d79e6
```
There are two possible causes of this. However, one of the solutions will *totally permanently brick your rpmdb* if used on the other problem.

### Case 1
In this most likely case - and the safest to fix - is that you've managed to get a half-upgraded package, which requires another one, but didn't use to. For this example, we'll assume `nss-softokn` was half upgraded, and the new version requires `nss-softokn-freebl`. To get out of this you must download the new depedency, and do some manual work to extract it:
```
mkdir /tmp/work
cd /tmp/work
yumdownloader nss-softokn-freebl
rpm2cpio nss-softokn-freebl-*x86_64.rpm | cpio -idmv
cp ./lib64/libfreeblpriv3.* /lib64
```
And that's it. Now `rpm -qa` should not give this error anymore. If it does, proceed to case two, with caution.

### Case 2
The other possible problem is a RPM database which is missing one or more pseudopackages which provides public keys.  Without those public keys, it'll probably have a hard time dealing with packages signed by certain sources. You can sort of fix this by first going onto a healthy machine and looking in `/etc/pki/rpm-gpg`.  Copy the right file or files onto the sick box and `rpm --import <that new file>`.  It should then recognize those packages as being associated with a given signer now.

## Missing dependencies for existing packages 
Some packages claim to not have all of their dependencies installed.
```
Package glibc-devel requires glibc = 2.5-24.el5_2.2
```

### Step 1: reinstall those packages so they will drag in those dependencies
This is easy to do with a simple pipeline:
```
package-cleanup --problems | awk '/^Package/{print $2}' | sort | uniq | xargs yum reinstall -y
```
If that finishes successfully, run `package-cleanup --problems` again and see what happens.  If it proclaims no problems, then go on to doing whatever you were trying to do originally.  It should succeed. If not, try more steps.

### Step 2: some package might fail in the above "reinstall the world" pass, so if so; do 'em one at a time and see how far you can get
```
package-cleanup --problems | awk '/^Package/{print $2}' | sort | uniq | xargs -n 1 yum reinstall -y
```
That's the same command as above with a `-n 1` to xargs to make a whole bunch of yum calls. Once this finishes, run `package-cleanup --problems` to see if anything is wrong. If it's clean, go back to whatever you were doing.  Otherwise, carry on.

### Step 3: if you got here, the different bits of the RPM database might be out of sync with each other
That is, the database itself (db4) is intact, but the data in it is wrong.  The only fix for that is a RPM db rebuild to get all of the pointers evened out.  (Clearly, they need foreign key constraints in their database.)
```
cd /var/lib/rpm && db_recover && rpm --rebuilddb
```
Assuming this doesn't blow up, then run `package-cleanup --problems` and see if there's anything to be done.  If it's clean, you're done.  Otherwise you need to try step 1 and maybe even step 2 again.

### Step 4: RPM db which isn't corrupted at the db4 level and isn't out of whack in terms of its own pointers
You probably have some mix of incompatible packages installed, perhaps by people using various "I know better than you do" override flags.

What you do now depends on the nature of the problem. You might see that there are two versions of the same package installed. Sometimes this actually happens, and other times it's because you have one version from arch A (32 bit i386/i686) and another version from arch B (x86_64). `rpm -q pkg` won't show this.  You need to give it some more magic to make it obvious.
```
rpm -q pkg --qf "%{NAME} %{VERSION} %{RELEASE} %{ARCH}\n"
```
Other times, you might see that `foo-12` is complaining about not having `foo-lib-12`, and the above steps won't fix it because `foo-12` is gone. At the same time, `foo-14` is also installed on the machine. In this case, the fix is easy: just remove `foo-12`. What happened here is that an upgrade from 12 to 14 went stupid after 14 went on, and before 12 came off.  Then 12 disappeared from yum at some point so the reinstall shortcut above would no longer work.

Fortunately, `package-cleanup` can help you here:
```
package-cleanup --cleandupes
```
It should offer to blow away the older versions (`foo-12`) while leaving the newer versions (`foo-14`) intact. You can also remove these by hand: `rpm -e <full package name, including version>` is what you want.

## ERROR with rpm_check_debug vs depsolve 
See an error like this when installing a package?
```
ERROR with rpm_check_debug vs depsolve:
rpmlib(FileDigests) is needed by foo-1.0.0-46.x86_64
rpmlib(PayloadIsXz) is needed by foo-1.0.0-46.x86_64
Complete!
(1, [u'Please report this error in https://bugzilla.redhat.com/enter_bug.cgi?product=Red%20Hat%20Enterprise%20Linux%205&component=yum'])
```
This usually means a package built on a CentOS 6 machine is trying to be installed on CentOS 5. Solutions are easy enough: you can find a 5 machine and rebuild it there, and then move your package into the separate 5 and 6 repos.  Or, you can do this in your spec file:
```
%_binary_filedigest_algorithm 1
%_source_filedigest_algorithm 1
%_source_payload w9.bzdio
%_binary_payload w9.bzdio
```
If you add the above to ~/.rpmmacros, it will automatically be added to your spec file upon creating an RPM, without any further action needed on your part.

## "package" has missing requires of "package" 
This is a special case of "the rpmdb is probably corrupt", so you may need to rebuild it. Since this can take a while, and makes it super unsafe for another thread to run, you need to grab the yum lock. Here's a command that grabs the lock if it's not there (kind of! note the TOUTTOC race):
```
if [ ! -f /var/run/yum.pid ]; then echo rebuilding db; ps -C bash -o pid= > /var/run/yum.pid && rpm --rebuilddb; rm -f /var/run/yum.pid; else echo yum lock held && false; fi
```

## IndexError: list index out of range 
This one seems to be limited to CentOS 5, and you usually find it when failing to upgrade a package. Then you try to `yum update -y foo` and hit this error
```
Loaded plugins: downloadonly, fastestmirror
Loading mirror speeds from cached hostfile
Setting up Update Process
Traceback (most recent call last):
  File "/usr/bin/yum", line 29, in ?
    yummain.user_main(sys.argv[1:], exit_code=True)
  File "/usr/share/yum-cli/yummain.py", line 309, in user_main
    errcode = main(args)
  File "/usr/share/yum-cli/yummain.py", line 178, in main
    result, resultmsgs = base.doCommands()
  File "/usr/share/yum-cli/cli.py", line 349, in doCommands
    return self.yum_cli_commands[self.basecmd].doCommand(self, self.basecmd, self.extcmds)
  File "/usr/share/yum-cli/yumcommands.py", line 202, in doCommand
    return base.updatePkgs(extcmds)
  File "/usr/share/yum-cli/cli.py", line 620, in updatePkgs
    if not self.update(pattern=arg):
  File "/usr/lib/python2.4/site-packages/yum/__init__.py", line 2865, in update
    (e, m, u) = self.rpmdb.matchPackageNames([kwargs['pattern']])
  File "/usr/lib/python2.4/site-packages/yum/packageSack.py", line 224, in matchPackageNames
    exactmatch.append(self.searchPkgTuple(pkgtup)[0])
IndexError: list index out of range
```
and can't go any further. This seems to be a problem in yum, and dcrpm won't see it. The fix is to rebuild your RPM database.
```
cp -a /var/lib/rpm /var/lib/rpm-backup-$(date +%s)
rpm --rebuilddb
```
Once that finishes, you should be able to do the yum update again.
