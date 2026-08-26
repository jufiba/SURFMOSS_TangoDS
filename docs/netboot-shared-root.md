# Raspberry Pi netboot with a shared NFS root (wolframite)

_Configuration validated 8-Aug-2026 (swap: 14-Aug-2026) on pi-rackmossbauer
(Pi 3B+, Debian 13 Trixie, arm64). Every production Pi in the lab is a 3B+, so one
root serves them all._

_Revised 23-Aug-2026: added the `machine-id`, per-host service activation and
package-installation sections, all three learned the hard way while bringing up
NUT on pi-leem._

---

## Design

A **single read-only shared root** (`/nfs/pi-trixie`) for all Pis, plus a
**per-Pi writable `/var`** mounted on top. Everything else (`/etc`, `/home`,
`/opt`, `/usr/local`) is common.

| What | Where | Mode |
|---|---|---|
| System root | `/nfs/pi-trixie` | `ro`, shared |
| `/var` (logs, state, the Starter's `ds.log`) | `/nfs/clients/<pi>/var` | `rw`, per-Pi |
| `/tmp` | tmpfs | volatile, automatic on Trixie |
| Device servers | `/opt/tango/SURFMOSS_TangoDS` + `/usr/local/bin` | common |

**Consequences of the design:**

- Updating software (`git pull`, `apt` in a container) is done **once** on
  wolframite and reaches every Pi at its next boot.
- A read-only root stops any single Pi from corrupting the common software. **All
  configuration changes happen on wolframite, never on the Pi** (`systemctl
  enable` and friends fail on the Pi because the root is `ro`).
- `/etc` is shared → every Pi shares the root password, `tangorc`, `resolv.conf`,
  `timesyncd.conf`. That is intentional: they are identical.
- **Identity (hostname) comes from DHCP**, not from `/etc/hostname` (which is
  deliberately empty). The name lives in exactly one place: `dhcp-host=` in
  `dnsmasq.conf`.
- **`/etc/machine-id` is deliberately empty too** — see the dedicated section
  below. This one is not optional; a shared machine-id breaks DHCP.
- Every Pi's logs are readable from wolframite under
  `/nfs/clients/<pi>/var/log/` — invaluable for debugging a Pi that won't boot.

---

## Pieces on wolframite

### 1. Exports (`/etc/exports`)

```
/nfs/pi-trixie   10.43.88.0/24(ro,sync,no_subtree_check,no_root_squash)

/nfs/clients/pi-rackmossbauer/var   10.43.88.11(rw,sync,no_subtree_check,no_root_squash)
```

The root is opened to the whole subnet because it is `ro` (no risk). Each `/var`
is restricted to that Pi's IP.

### 2. systemd generator (in the shared root)

`/nfs/pi-trixie/etc/systemd/system-generators/nfs-var-generator` (must be
executable, `chmod +x` — without it systemd ignores the file silently).

It builds the `/var` path from the hostname, so **one file serves every Pi**:

```sh
#!/bin/sh
# Generate the /var mount from /nfs/clients/<hostname>/var
set -e
DEST="$1"
[ -n "$DEST" ] || exit 0

HN=$(cat /proc/sys/kernel/hostname 2>/dev/null)
case "$HN" in
  ""|localhost|"(none)") exit 0 ;;
esac

cat > "$DEST/var.mount" <<UNIT
[Unit]
Description=NFS /var for $HN
After=network.target

[Mount]
What=10.43.88.3:/nfs/clients/$HN/var
Where=/var
Type=nfs
Options=vers=4.1,rw,_netdev,addr=10.43.88.3

[Install]
WantedBy=remote-fs.target
UNIT

mkdir -p "$DEST/remote-fs.target.requires"
ln -sf "$DEST/var.mount" "$DEST/remote-fs.target.requires/var.mount"
```

⚠️ **Two details that cost hours of debugging:**

1. **`addr=` is mandatory** in the options. Without it:
   `NFS: mount program didn't pass remote address`. With `proto=tcp` in its
   place: `NFS: Server address does not match proto= option`.
2. **Do NOT use `DefaultDependencies=no` + `Before=local-fs.target`.** A network
   mount belongs to `remote-fs.target`, after the network is up. Attempted too
   early it fails and the system drops into emergency mode with cascading
   failures (console-setup, cloud-init).

Note that this generator reads `/proc/sys/kernel/hostname`, not the systemd
hostname. That turns out to be the reliable source on this fleet — see
"Per-host service activation" below.

### 3. Named DHCP reservation (`dnsmasq.conf`)

The hostname arrives over DHCP, so the reservation **must include the name**:

```
dhcp-host=b8:27:eb:a9:82:05,pi-rackmossbauer,10.43.88.11,infinite
```

Without the name the generator doesn't know which path to mount and exits doing
nothing.

⚠️ **`,infinite` is required on every Pi.** The kernel's `ip=dhcp` configures the
interface once at boot and never renews. When a finite lease expires dnsmasq
stops serving that name, the Pi vanishes from DNS, and `sudo` starts complaining
that it cannot resolve the local host. Infinite leases show `0` in the expiry
field of `/var/lib/misc/dnsmasq.leases`.

### 4. Per-Pi TFTP directory

`/tftpboot/<serial>/` with the Trixie firmware. Key points:

- **`config.txt`** must have `arm_64bit=1` (arm64 root on a Pi 3B+). Keep
  `dtoverlay=w1-gpio,gpiopin=4` where TempSensorDS18B20 is in use — but note it
  conflicts with GPIO 4 used for other purposes, so it is per-Pi, not universal.
- **`cmdline.txt`**:
  ```
  console=serial0,115200 console=tty1 root=/dev/nfs nfsroot=10.43.88.3:/nfs/pi-trixie,vers=4.1,proto=tcp rw ip=dhcp rootwait
  ```
- The firmware (`start*.elf`, `fixup*.dat`, `kernel8.img`, `.dtb`, `overlays/`)
  is obtained in the container with
  `apt install --reinstall raspi-firmware linux-image-rpi-v8`
  and copied from `/nfs/pi-trixie/boot/firmware/`.
- **No initrd needed**: with `root=/dev/nfs` + `ip=dhcp` the kernel mounts the
  root directly. (`mkinitramfs` fails in a container and on an NFS root — that is
  expected.)

⚠️ **`config.txt` is per-Pi**, living under `/tftpboot/<serial>/`.
`/nfs/pi-trixie/boot/firmware/config.txt` is *not* read at boot. `cmdline.txt` is
identical across Pis.

---

## `/etc/machine-id` must be empty

**This is the single most damaging trap in the whole design, and it hid for
months.** Diagnosed 22-Aug-2026.

### Symptoms

- Pis "disappear" from the network after some time — unreachable by name,
  missing from `/var/lib/misc/dnsmasq.leases` even while up and running.
- `sudo` on the affected Pi complains that it cannot resolve its own hostname.
- The failure moves around: whichever Pi lost the last round is the broken one.

### Cause

The DHCP client derives its DUID from `/etc/machine-id`. Because `/etc` lives in
the shared root, **every netboot Pi presented the same DUID** to dnsmasq, which
therefore treated them as one client whose lease kept being reassigned. The
microSD Pis were unaffected: they identify by MAC (`01:<mac>`) rather than DUID.

The tell is in the lease file. Before the fix:

```
pi-leem   ff:e7:8f:17:65:00:02:00:00:ab:11:c0:39:f7:59:be:b2:5c:97
pi-uno    ff:f8:ce:1b:a1:00:02:00:00:ab:11:c0:39:f7:59:be:b2:5c:97
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                          identical tail = same machine-id
```

`00:02` is DUID type 2, `00:00:ab:11` is enterprise number 43793 (systemd), and
the last eight bytes come from the machine-id. Only the leading IAID differs.

### Fix

```bash
sudo truncate -s 0 /nfs/pi-trixie/etc/machine-id
ls -l /nfs/pi-trixie/etc/machine-id     # 0 bytes, mode 444 is correct
```

An empty (zero-length) `machine-id` is a documented, valid state: systemd reads
it as "uninitialised" and generates a fresh one at boot. On a read-only root it
cannot write to `/etc`, so it mounts a transient `/run/machine-id` instead —
different on every Pi, regenerated on every boot. Exactly the same pattern
already used for `/etc/hostname`.

After the fix the DUID tails diverge:

```
pi-rackmossbauer  ...ab:11:c3:16:da:d8:8c:6b:d2:1e
pi-leem           ...ab:11:c0:39:f7:59:be:b2:5c:97
```

### Two things to check alongside

- `/var/lib/dbus/machine-id` must be a **symlink** to `/etc/machine-id`, in the
  shared-root template *and* in every `/nfs/clients/<pi>/var/`. If it is a
  regular file with the old value, dbus keeps handing out the shared id.
- The machine-id now changes on every boot, so anything keying persistent state
  off it will fragment. The main case is the journal, which writes to
  `/var/log/journal/<machine-id>/`. Since `/var` is already per-Pi the damage is
  contained, but old directories will accumulate.

⚠️ Each Pi keeps the old shared id until it reboots. Fixing the file on
wolframite is not enough — the fleet has to cycle.

---

## Per-host service activation

`/etc` is shared, so enabling a service enables it on all seven Pis. Some
services belong to exactly one machine (the UPS driver on pi-leem, the synoptic
on the three panel Pis). Two mechanisms, one of which does not work.

### ❌ `ConditionHost=` is not reliable here

`ConditionHost=pi-leem` in a drop-in evaluates to **`no` during early boot** and
`yes` once the system is up. Verified both ways:

```bash
# on a fully booted pi-leem — works
sudo systemd-run --unit=condtest -p ConditionHost=pi-leem /bin/true
systemctl show condtest -p ConditionResult      # yes

# same condition on a service reached early in boot
systemctl show nut-server -p ConditionResult    # no
```

The likely reason is that these Pis have no static hostname
(`hostnamectl` reports `Static hostname: (unset)`, `Transient hostname: pi-leem`)
because the name arrives from DHCP, and the transient name is not yet visible to
systemd when early units are evaluated. **The mechanism was never fully pinned
down** — what matters is that the condition silently fails at boot and silently
succeeds afterwards, which makes it look like it works when tested by hand.

It does work correctly in the *negative* direction — a Pi that is not the target
host always skips — so validating on a non-target Pi proves nothing.

### ✅ `ExecCondition=` reading `/proc/sys/kernel/hostname`

Same source the `/var` generator uses, and it is populated by the time any
service starts. Helper, installed once in the shared root:

```sh
#!/bin/sh
# /usr/local/sbin/host-is  (chmod 755)
[ "$(cat /proc/sys/kernel/hostname)" = "$1" ]
```

Drop-in for any service that should run on one host only:

```ini
[Unit]

[Service]
ExecCondition=/usr/local/sbin/host-is pi-leem
```

A non-zero exit skips the service cleanly, without marking it failed, and it
leaves a journal entry — unlike `ConditionHost=`, which in the failure mode above
logged nothing at all.

This is the pattern to use for the synoptic autostart on the panel Pis.

### ⚠️ `Wants=` from a package's own target may not fire

Separate, still-unexplained problem found with NUT. `nut.target` was reached at
boot, `systemctl show nut.target -p Wants` correctly listed `nut-server.service`,
the `nut.target.wants/` symlink existed, and the service was `enabled` — yet
systemd never even attempted to start it (zero journal entries, no condition
check logged).

Worked around by linking the service directly into `multi-user.target`, in the
shared root:

```bash
cd /nfs/pi-trixie/etc/systemd/system
sudo mkdir -p multi-user.target.wants
sudo ln -sf /usr/lib/systemd/system/nut-server.service \
            multi-user.target.wants/nut-server.service
```

If a package's service refuses to start at boot despite everything looking
correct, try this before investigating further.

---

## Installing packages into the shared root

Use **`systemd-nspawn`, not manual `chroot`**:

```bash
sudo systemd-nspawn -D /nfs/pi-trixie
```

nspawn mounts and unmounts `/dev`, `/proc` and `/sys` by itself, avoiding the
bind-mount leakage that manual chroot causes. Two things to know:

- ⚠️ **nspawn silently overwrites `/nfs/pi-trixie/etc/resolv.conf`** with
  wolframite's copy. Wolframite points at `127.0.0.1` (its own dnsmasq), which is
  meaningless on a Pi — this breaks DNS fleet-wide at the next boot. **Verify
  after every nspawn session**, especially after a dirty exit:
  ```bash
  cat /nfs/pi-trixie/etc/resolv.conf
  # must be:  domain lab / nameserver 10.43.88.3
  ```
- A dropped SSH session leaves the container running. `machinectl list` shows it;
  `sudo machinectl terminate pi-trixie` closes it.

### ⚠️ NFSv4 leases break `groupadd` / `useradd`

Any package whose postinst creates a system user fails inside the container:

```
groupadd: cannot open /etc/group: Resource temporarily unavailable
fatal: `/sbin/groupadd -g 106 nut' returned error code 10. Exiting.
dpkg: error processing package nut-client (--configure): ... exit status 82
```

The cause is visible only under `strace`:

```
openat("/etc/group", O_RDWR|O_NOCTTY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC) = -1 EAGAIN
```

`O_NONBLOCK` on a regular file means: if the inode has a lease, return `EAGAIN`
immediately instead of waiting for it to be broken. `nfsd` hands out NFSv4
delegations on files the booted Pis are reading, and `/etc/group` is one of them.

This is invisible to normal debugging: `lsof` and `fuser` show nothing (the
holder is a remote client, not a local process), `/proc/locks` shows nothing at
any given instant (delegations come and go), and there are no stale `.lock`
files.

**Fix — disable leases for the duration of the install:**

```bash
cat /proc/sys/fs/leases-enable          # note the value (1)
echo 0 | sudo tee /proc/sys/fs/leases-enable
# ... install / dpkg --configure -a inside the container ...
echo 1 | sudo tee /proc/sys/fs/leases-enable
```

Delegations are a caching optimisation, not a requirement; the Pis keep working
without them, at the cost of a little more revalidation traffic. The setting is
not persistent, so a reboot of wolframite restores it — but restore it by hand
anyway.

**Alternative — run the tool from wolframite with `--root`**, which also works
and needs no NFS changes:

```bash
sudo /sbin/groupadd --root /nfs/pi-trixie -g 106 nut
sudo /sbin/useradd  --root /nfs/pi-trixie -r -d /var/lib/nut -g nut \
                    -s /usr/sbin/nologin -u 103 nut
```

Then `dpkg --configure -a` inside the container: the postinst finds the user and
group already present and skips creating them.

### Benign messages when configuring packages in a container

- `invoke-rc.d: could not determine current runlevel` — normal, no running
  systemd.
- `Failed to preset unit: Unit X is masked` — expected if you masked it on
  purpose.

---

## Adding a new Pi

Three steps on wolframite; the generator does the rest.

```bash
PI=pi-vsm
IP=10.43.88.12

# 1. Per-Pi /var, seeded from the shared root
#    (check first that /nfs/pi-trixie/var/swap does NOT exist — see the swap section)
sudo mkdir -p /nfs/clients/$PI/var
sudo rsync -aHAX /nfs/pi-trixie/var/ /nfs/clients/$PI/var/

# 2. Export
echo "/nfs/clients/$PI/var   $IP(rw,sync,no_subtree_check,no_root_squash)" \
  | sudo tee -a /etc/exports
sudo exportfs -ra

# 3. Named DHCP reservation in dnsmasq.conf, then reload
#    dhcp-host=<MAC>,$PI,$IP,infinite
sudo systemctl reload dnsmasq
```

Plus the TFTP directory `/tftpboot/<serial>/` with the Trixie firmware (copy from
an already-migrated Pi and adjust nothing — `cmdline.txt` and `config.txt` are
the same for all, because identity comes from DHCP).

Seeding `/var` by rsync copies whatever logs the source Pi had. Harmless, but
`ds.log/` will contain another Pi's device-server logs until they age out —
don't be misled when debugging.

---

## Verification after a Pi boots

```bash
hostname                    # should come from DHCP
mount | grep /var           # should mount /nfs/clients/<pi>/var
timedatectl status          # System clock synchronized: yes
systemctl --failed          # see below for what is expected
```

Also worth checking on wolframite, after the machine-id fix:

```bash
grep <pi-name> /var/lib/misc/dnsmasq.leases   # expiry field must be 0
```

### Expected, benign failures

| Service | Reason | Fix |
|---|---|---|
| `bluetooth.service` | Unused on the Pis | `rm /nfs/pi-trixie/etc/systemd/system/bluetooth.target.wants/bluetooth.service` |
| `console-setup.service` | Needs to write to `/etc` (`ro`) | `ln -sf /dev/null /nfs/pi-trixie/etc/systemd/system/console-setup.service` |
| `systemd-networkd-wait-online` | The kernel configures the network (`ip=dhcp`), not networkd; it waits for something that never arrives | Mask it, or ignore (cosmetic) |

### Clock skew in early journal entries

The Pis have no RTC. They start with whatever time they had and only correct it
once timesyncd reaches NTP, so early boot entries carry a stale date — sometimes
days old. Comparing timestamps across the boot is misleading until the sync
line appears.

---

### pi-uleem: netboots (resolved)

Resolved by 26-Aug-2026. `pi-uleem.lab` boots from the shared root with no
microSD; confirmed by its `/` mount (`10.43.88.3:/nfs/pi-trixie`) and by the
shared-root ssh host key it now presents.

**`pi-hvleem` is the only one still on microSD.**

Note that every netbooting Pi serves `/etc/ssh/ssh_host_*` from the shared root
and so presents the *same* host key. Converting a Pi to netboot therefore trips
"REMOTE HOST IDENTIFICATION HAS CHANGED" on the first ssh. Compare the offered
fingerprint against `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on a Pi
that is already reachable before clearing anything; if they match it is the
shared root, and `ssh-keygen -R <host>` is the fix.

---

## Shared-root customisation (once, applies to all)

Already applied in `/nfs/pi-trixie`:

- `/etc/hostname` **empty** → the name comes from DHCP.
- `/etc/machine-id` **empty** → per-boot transient id. See the dedicated section;
  this is mandatory, not cosmetic.
- `/etc/resolv.conf` → `nameserver 10.43.88.3` + `domain lab`. Re-check after any
  nspawn session.
- `/etc/systemd/timesyncd.conf` → `NTP=tangodb.lab`. **timesyncd ignores the DHCP
  NTP option**, it has to be set explicitly.
- `/etc/tangorc` → `TANGO_HOST=tangodb.lab:10000`. Note JTango reads
  `/etc/tangorc` at *higher* priority than the `TANGO_HOST` environment variable —
  the opposite of cppTango — so it must stay consistent everywhere.
- User `pi`: the RaspiOS image ships it with `/usr/sbin/nologin` and `!` in
  shadow; complete it with the first-boot wizard or by editing `passwd`/`shadow`
  from wolframite.
- Root password: hash in `/nfs/pi-trixie/etc/shadow` (shared by all Pis). Needed
  to get into emergency mode if something breaks.
- `tango-starter` installed, with the unit copied to `/etc/systemd/system/` and
  the `Requires=tango-db.service` line removed (a drop-in with an empty
  `Requires=` does **not** cancel it).
- `/usr/local/sbin/host-is` — per-host activation helper, see above.
- **Swap**: `Mechanism=zram` in an `rpi-swap` drop-in (see below). Without it each
  Pi creates a 1–2 GB writeback file in its NFS `/var`.
- `/etc/udev/rules.d/99-pfeiffer-delphin.rules` — binds `ftdi_sio` to the TU400's
  converter, which has a PID the driver does not know. See below.

### ⚠️ A USB-serial converter with an unrecognised PID gets no `/dev` entry

`PfeifferTU400/1` on pi-leem died at start with

```
Can't open /dev/serial/by-path/platform-3f980000.usb-usb-0:1.1.2:1.0-port0:
[Errno 2] No such file or directory
```

The property was right and the cable was in. `1-1.1.2` was present in
`/sys/bus/usb/devices`, but with **no driver bound**:

```
1-1.1.2    0403:daf1  drv=NONE  tty=none  Delphin USB Serial Converter 09QC4001
```

It is an FTDI part (vendor `0403`) reflashed with a vendor product id, `daf1`,
which is not in the `ftdi_sio` table. The kernel enumerates the device, nothing
claims it, and so no `ttyUSB` and no `/dev/serial/by-path` entry ever appear.
Nothing is logged as an error — the port is simply absent.

Fix, in `/nfs/pi-trixie/etc/udev/rules.d/99-pfeiffer-delphin.rules`:

```
ACTION=="add", SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="0403", ATTR{idProduct}=="daf1", RUN+="/sbin/modprobe ftdi_sio", RUN+="/bin/sh -c \x27echo 0403 daf1 > /sys/bus/usb-serial/drivers/ftdi_sio/new_id\x27"
```

`\x27` is how udev spells a single quote inside `RUN+=`; a literal `'` there
does not parse. Once `new_id` accepts the pair, `ftdi_sio` binds this converter
and any other with the same PID.

To try it on a running Pi without touching the read-only root, drop the same
file in `/run/udev/rules.d/` (tmpfs, writable, gone at reboot), then
`sudo udevadm control --reload` and re-enumerate the device with

```
echo 0 | sudo tee /sys/bus/usb/devices/1-1.1.2/authorized
echo 1 | sudo tee /sys/bus/usb/devices/1-1.1.2/authorized
```

A one-off bind without any rule is `echo "0403 daf1" | sudo tee
/sys/bus/usb-serial/drivers/ftdi_sio/new_id` — useful for a quick check, but it
is lost at the next reboot.

### ⚠️ Swap: force `Mechanism=zram` (rpi-swap)

On Trixie swap is managed by **`rpi-swap`** (which replaces `dphys-swapfile`, now
gone). Its default `Mechanism=auto` currently resolves to **`zram+file`**: it
creates a `/dev/zram0` and also a `/var/swap` file that zram uses as
**writeback**, to offload inactive pages. The file is sized from each board's RAM:
**905 MB on the 3B+ and 2 GB on the Pi 4.**

Two problems with this setup:

1. **Space.** The file lives in `/nfs/clients/<pi>/var`, so each Pi costs ~1.9 GB
   instead of ~450 MB. Across the whole fleet that is several GB of pure waste.
   (Found 14-Aug-2026: it was 80 % of what the `/var` directories occupied.)
2. **Deadlock risk.** The writeback goes **over the network**. The kernel would
   end up needing NFS I/O to free memory, exactly when memory is under pressure —
   a deadlock candidate. With pure zram that path does not exist.

`rpi-swap`'s stated rationale for `zram+file` is **reducing microSD wear** through
infrequent writes. Netboot Pis have no SD card to protect, so only the cost
remains.

Drop-in in the shared root (serves every Pi), from wolframite:

```bash
mkdir -p /nfs/pi-trixie/etc/rpi/swap.conf.d
cat > /nfs/pi-trixie/etc/rpi/swap.conf.d/10-zram-only.conf <<'EOF'
# Netboot Pis: /var lives on NFS.
# Pure zram — no writeback file, which would go over the network.
[Main]
Mechanism=zram
EOF
```

⚠️ **Set it explicitly, do not rely on `auto`.** The `swap.conf(5)` man page warns
that the value `auto` resolves to may change in future versions; without the
drop-in, an `rpi-swap` update would reintroduce the file on every Pi at once.

**Delete the files only with the Pi powered off or already rebooted.**
`/var/swap` is attached to a `/dev/loopN` that is zram0's `backing_dev`; deleting
it while live leaves the inode dangling. Correct order:

```bash
# 1. Reboot the Pi after creating the drop-in, then verify on it:
cat /sys/block/zram0/backing_dev   # must say 'none'
losetup -a                          # no loop over /var/swap
swapon --show                       # only /dev/zram0

# 2. Only then, from wolframite:
rm -f /nfs/pi-trixie/var/swap /nfs/clients/*/var/swap
```

Verified 14-Aug-2026: the `/var` directories went from ~1.9 GB to ~450 MB per Pi.

---

## X11 and synoptics (panel Pis)

Three of the Pis act as **status panels** with a monitor, showing an ATK synoptic
in addition to running their device servers.

### Java and Tango jars

RaspiOS Lite ships no Java. Install `default-jre` (modern Trixie Java; **Java 8 is
gone from Debian**, so the old `libtango-java` jars — a ten-year-old `.deb`,
outside Debian and outside current Tango releases — are not an option).

New jars, from `gitlab.com/tango-controls`, in `/usr/share/java`:

| Jar | Unversioned symlink | Note |
|---|---|---|
| `ATKCore-9.4.20.jar` | `ATKCore.jar` | |
| `ATKWidget-9.4.20.jar` | `ATKWidget.jar` | |
| `Jive-7.46-jar-with-dependencies.jar` | `JTango.jar` | ⚠️ see below |

⚠️ **The `JTango.jar` symlink points at Jive's fat jar on purpose.**
`JTangoClientLang-10.0.0-rc1.jar` is **not** enough: it lacks the CORBA IDL
classes (`fr.esrf.Tango.DevError`) and startup fails with `NoClassDefFoundError`.
On Maven Central the `JTango` artifact is only an aggregator POM (no jar), and
assembling the individual modules (TangORB, JavaTangoIDL, JTangoCommons…) drags in
a dependency chain. Jive's fat jar contains all 2178 `fr/esrf` classes and
resolves everything at once.

The `synopticappli` script (in `/usr/local/bin`) works unchanged, because it looks
for `JTango.jar`, `ATKCore.jar` and `ATKWidget.jar` in `/usr/share/java`.

The `.jdw` files live in `/opt/tango/SURFMOSS_TangoDS/synoptics/`.
Validated 10-Aug-2026: `mossbauer.jdw` starts on Trixie with modern Java.

### X11 packages (minimal, no desktop)

```bash
sudo apt install --no-install-recommends \
  xserver-xorg xinit x11-xserver-utils matchbox-window-manager
```

- `x11-xserver-utils` provides `xset`, needed to disable the screensaver and DPMS
  on a panel that must stay visible.
- `matchbox-window-manager` is built for panels/kiosks: fullscreen windows, no
  decoration, no menus.
- `--no-install-recommends` is **essential**: without it half a desktop comes
  along.
- X11 forwarding over SSH needs `xauth` (on the intermediate hops too, e.g.
  wolframite).

### Per-Pi autostart — solved, pending deployment

Because `/etc` is shared, enabling synoptic autostart would affect all seven Pis
rather than the three with monitors. **The mechanism is now settled**: use
`ExecCondition=/usr/local/sbin/host-is <pi>` in the unit, per the "Per-host
service activation" section. `ConditionHost=` must not be used — it fails
silently at boot.

Still to be deployed as of 23-Aug-2026.

---

## Recovery

- **TFTP directory backups**: `/tftpboot/<serial>.trixie` (Debian 13) and
  `/tftpboot/<serial>.debian10` (old root). Reverting to either is one
  `rsync -a --delete`.
- **Emergency mode** asks for the root password. If the account is locked (`*` or
  `!` in shadow) there is no way in — hence the importance of having the hash set.
  Note the shadow the Pi uses is the **shared root's**, not
  `/nfs/clients/<pi>/etc/` (that directory is left over from an earlier
  experiment and is not mounted).
- **Unplugging the network with the NFS root mounted hangs the Pi** and may leave
  it in emergency mode on the next boot. Do not hot-unplug.
- To disable the scheme and go back to a monolithic root: `chmod -x` the
  generator and set the `/nfs/pi-trixie` export to `rw`.

---

## Open items

- Convert the remaining three Tango microSD Pis to netboot (pi-xps, pi-mossbauer,
  pi-hvleem): create their `/tftpboot/<serial>/` and record their MACs.
- **`ender` stays out of this scheme**: it is the 3D printer controller (it runs no
  device servers) and needs a writable root for its configuration and gcode files.
  It keeps its microSD at `10.43.88.16`.
- **Reboot the five Pis still carrying the old shared machine-id** so they pick up
  their own. Until then they keep colliding with each other over DHCP.
- Deploy the synoptic autostart using the `host-is` pattern.
- Decide whether `/home` deserves to be per-Pi (currently shared; with a single
  `pi` user and little content, it doesn't seem necessary).
- `/var/lib/systemd` sits inside the per-Pi `/var`, so systemd and timesyncd state
  is already individual. Correct as is.
- Unexplained: why `nut.target` did not pull `nut-server` at boot, and why
  `ConditionHost=` evaluates false during early boot. Both worked around, neither
  understood.

---

## Pi 4: enabling netboot

The Pi 4 bootloader (SPI EEPROM) does not ship with netboot enabled. With a
RaspiOS SD card, once per board:

    sudo rpi-eeprom-update -a && sudo reboot
    sudo -E rpi-eeprom-config --edit    # add BOOT_ORDER=0xf21
    vcgencmd otp_dump | grep 28:        # serial → TFTP directory name
    ip link show eth0 | grep ether      # MAC → dhcp-host

⚠️ **Do NOT set `TFTP_PREFIX=1`.** The default (`0`) is already correct: it
prefixes with the serial number, same as the 3B+. `1` means "use
`TFTP_PREFIX_STR`", and with that variable undefined the prefix is empty → the Pi
requests `/tftpboot/start4.elf` and fails with "Firmware not found". (`2` = MAC.)

The TFTP directory is created by copying from the root, not from a 3B+ — it needs
`start4.elf`, `fixup4.dat` and `bcm2711-rpi-4-b.dtb`:

    sudo rsync -a /nfs/pi-trixie/boot/firmware/ /tftpboot/<serial>/

`cmdline.txt` and `config.txt` are not in the root (the installer generates them,
not `raspi-firmware`): copy them from a working 3B+ directory. They are identical
across Pis; identity comes from DHCP.

**Validated**: pi-test (`ed8dd269`, `dc:a6:32:89:e7:1d`, `10.43.88.21`), Aug-2026.
