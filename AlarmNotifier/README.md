# AlarmNotifier

Watches the `State` of other device servers and sends e-mail. A deliberately
small replacement for PANIC/PyAlarm.

It does not evaluate numeric thresholds. That judgement belongs to
`AnalogInterlock` instances running watch-only on the instrument's own Pi,
where it keeps working if this server or the network is down. Here only
verdicts already reached elsewhere are read.

**It does not act.** Anything that must interrupt an experiment belongs in an
interlock; anything that must not happen at all belongs in a hardware chain.

## Installing in the repository

Put `AlarmNotifier/` at the top of `SURFMOSS_TangoDS` and add one line to each
of three sections of `pyproject.toml`. In all three it goes directly after
`AGPolaritySwitch`, which precedes it alphabetically.

```toml
[project.scripts]
# AlarmNotifier
AlarmNotifier = "AlarmNotifier:main"
```

```toml
[tool.setuptools]
packages = [
    "AGPolaritySwitch",
    "AlarmNotifier",
    "AMLPGC1",
```

```toml
[tool.setuptools.package-dir]
AlarmNotifier        = "AlarmNotifier/AlarmNotifier"
```

No new dependencies: standard library and PyTango.

⚠️ This server runs on **wolframite**, not on a Pi, so it is not installed into
the shared NFS root. Use a clone kept separate from your working copy, so that
`git pull` there is the deliberate act of deploying and a half-finished edit
elsewhere never becomes what the alarm system runs.

```bash
sudo git clone <repo-url> /opt/tango/SURFMOSS_TangoDS
cd /opt/tango/SURFMOSS_TangoDS
sudo pip install --no-deps --break-system-packages -e .
```

`--no-deps` is not optional. `pyproject.toml` declares `pytango`, and without
the flag pip fetches a wheel into `/usr/local/lib/python3/dist-packages`, which
precedes `/usr/lib/python3/dist-packages` on `sys.path`. The Debian
`python3-tango` would then be silently shadowed. Check both after installing:

```bash
which AlarmNotifier                              # /usr/local/bin/AlarmNotifier
python3 -c "import tango; print(tango.__file__)" # must still be /usr/lib/...
```

## Registering

Server `AlarmNotifier/lab`, class `AlarmNotifier`, device `lab/alarm/notifier`.

Add it to the Starter's controlled list in Astor, start level 1.

⚠️ wolframite has two Starter entries in the database. The live one is
`tango/admin/wolframite`, without the domain; `tango/admin/wolframite.lab` is
an empty registration that has never run. Use the former.

### Domain convention

| Scope | Domain | Example |
|---|---|---|
| An instrument's safety chain | `<instrument>/safety/` | `xps/safety/interlockxraygun` |
| Watching that only warns | `<instrument>/warn/` | `mossbauer/warn/watercompressor` |
| Lab-wide service | `lab/` | `lab/alarm/notifier` |

`warn/` describes what the device does rather than what it measures: its output
is a warning, not a permissive. A watch-only device under `safety/` would
suggest a line is protected when it is merely watched.

`tango/` and `sys/` are reserved for Tango's own infrastructure.

### Why under the Starter rather than its own systemd unit

A unit with `Restart=always` would survive the Starter dying, which otherwise
takes the notifier with it and leaves exactly silence. It still goes under the
Starter, because anyone in the lab can see it and restart it from Astor
alongside everything else, whereas a systemd unit on wolframite is only usable
by someone with an account who knows it exists. An alarm system that depends on
one person is fragile in a different way.

What that choice gives up is already covered by `ReportSchedule`: if the
Starter falls it takes the notifier with it, Monday's report does not arrive,
and that absence is the alarm.

## Prerequisite: msmtp usable by the tango user

`msmtp` configured on wolframite with `/usr/sbin/sendmail` available. See
`notificaciones-gmail-linux.md`.

⚠️ The Starter runs as `User=tango`, and `/etc/msmtprc` is `600 root:root`
because msmtp refuses a configuration file readable by others if it holds the
password. Separate the credential rather than loosening the file:

```bash
sudo sh -c 'grep "^password" /etc/msmtprc | awk "{print \$2}" > /etc/msmtp-password'
sudo chown root:tango /etc/msmtp-password
sudo chmod 640 /etc/msmtp-password
# in /etc/msmtprc, replace the password line with:
#   passwordeval cat /etc/msmtp-password
sudo chmod 644 /etc/msmtprc
```

The log needs to be writable by tango too. Check the real path in the `logfile`
directive of `/etc/msmtprc`: on wolframite it is `/var/log/msmtp`, without the
`.log`.

```bash
sudo chown root:tango /var/log/msmtp
sudo chmod 660 /var/log/msmtp
```

A log it cannot write is worth getting right, because msmtp sends the mail
anyway and still exits 0. The failure never reaches `LastMailError`; it is lost
in silence.

Test **as the tango user**, not as root and not as yourself:

```bash
sudo -u tango /usr/sbin/sendmail -t <<'EOF'
To: somewhere@example
Subject: test

test
EOF
sudo journalctl -k --since "2 min ago" | grep DENIED
sudo tail -3 /var/log/msmtp
```

`DENIED` on `/bin/cat` or `/etc/msmtp-password` is msmtp's AppArmor profile,
which distrusts `passwordeval` invoking external programs. Add those paths to
the profile rather than reverting.

If that mail does not arrive, neither will this server's.

There is no logrotate configuration for `/var/log/msmtp` on wolframite, so it
grows without bound. At this volume that is years away, but if one is added
later it must carry `create 660 root tango` or the permissions revert and the
logging breaks again unnoticed.

## Minimum configuration in Jive

| Property | Value |
|---|---|
| `Recipients` | one address per element |
| `Rules` | one rule per element (see below) |
| `ReportSchedule` | `mon 08:00` |

⚠️ `Rules` and `Recipients` are **string arrays**. In Jive each element goes on
its own line. They are `dtype=('str',)` deliberately: with `'str'` PyTango keeps
only the first element and every rule but one would vanish, without an error.

## Rule format

Space-separated `key=value` pairs. `msg=` goes **last**, because it swallows
the rest of the line. Blank lines and lines starting with `#` are skipped.

```
name=xpsWater dev=xps/safety/interlockxraygun alarm=ALARM,FAULT ok=ON ctx=xps/safety/water/xray msg=XPS water interlock tripped
```

| Field | Req. | Default | Meaning |
|---|---|---|---|
| `name` | yes | — | Unique. What `Snooze` and `Acknowledge` take. |
| `dev` | yes¹ | — | Device whose `State` is watched. |
| `attr` | yes¹ | — | `domain/family/member/attribute`, for `op=edge`. |
| `op` | no | `state` | `state` or `edge`. |
| `alarm` | no | `ALARM,FAULT` | States that trip. |
| `ok` | no | `ON` | States that count as recovered. |
| `persist` | no | `2` | Consecutive sweeps before tripping. |
| `enabled` | no | `yes` | `no` leaves it inert but visible. |
| `onunknown` | no | `alarm` | `ignore` when the device is switched off on purpose. |
| `to` | no | — | **Replaces** `Recipients`. |
| `cc` | no | — | **Adds to** `Recipients`. |
| `ctx` | no | — | Attributes to read into the mail body. |
| `msg` | no | `name` | Subject text. Goes last. |

¹ `dev` for `op=state`, `attr` for `op=edge`.

A state in neither `alarm=` nor `ok=` (`INIT`, `MOVING`) **holds** the rule
where it was: it neither trips nor recovers. That is what keeps an `Init` from
Jive out of your inbox.

A malformed rule leaves the device in `FAULT` with the offending line in
`Status`. It is never skipped silently, because that is how an alarm gets lost.

## Commands

| Command | Argument | Effect |
|---|---|---|
| `Snooze` | `[name, hours]` | Sleeps a rule. Refuses more than `MaxSnoozeHours`. |
| `Wake` | `name` | Wakes it early. |
| `Acknowledge` | `name` | Silences reminders; the alarm stays active and visible. |
| `AcknowledgeAll` | — | For a bad morning. |
| `Report` | — → `str` | The status table, readable from Jive. |
| `TestMail` | — | Sends the report now. |
| `SendMessage` | `[subject, body]` | Arbitrary mail. **Not to be called from the loop of a safety device server.** |
| `ReloadRules` | — → `str` | Re-reads `Rules` without an `Init`, keeping the running state of every rule whose text is unchanged. |

## Test procedure

1. `TestMail` from Jive. A mail with the rule table should arrive. If not,
   check `LastMailError` and `sudo tail /var/log/msmtp`.
2. With the XPS interlock in `ON`, `Report` should show `xpsWater NORM`.
3. `Trip` on `xps/safety/interlockxraygun`. After two sweeps (`persist=2`, 20 s)
   the ALARMA mail should arrive, with the flow in the context block.
4. `Reset` on the interlock. The RESUELTO mail should arrive.
5. Stop `AnalogInterlock/1` from Astor. After five minutes
   (`UnknownCycles=30` × 10 s) the SIN LECTURA mail should arrive. **This is
   the step that justifies the whole exercise**: it is the failure a
   threshold-based watchdog cannot see.
6. `Snooze ["xpsWater", "0.05"]` (3 min), repeat step 3, and confirm nothing
   arrives. It wakes by itself.
7. Restart the server with a snooze live and confirm the rule is still asleep:
   `SnoozeState` is memorized and comes back from the database.

`sys/tg_test/1` is registered on wolframite and makes a convenient target for a
throwaway rule if you want to rehearse step 5 without stopping anything real.

## Who watches the watcher

If this server dies you stop getting mail, and that looks a great deal like
everything being fine.

- `UpdateCount` is published as a heartbeat, for something else to look at.
- The `ReportSchedule` mail is what actually closes the loop: **if a Monday
  passes with no mail at all, that is the alarm.** Which is why leaving
  `ReportSchedule` empty is a worse idea than it appears.

A watch-only `AnalogInterlock` pointed at this `UpdateCount` will detect the
freeze but cannot report it: whoever would read its `ALARM` is precisely the
thing that is dead. Useful for the synoptic panel, not for mail.
