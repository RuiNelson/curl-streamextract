---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Long: ftp-mc-stripe
Arg: <size>
Help: FTPMC stripe size
Protocols: FTP
Added: 8.23.0
Category: ftp
Multi: single
See-also:
  - ftp-mc
Example:
  - --ftp-mc 4 --ftp-mc-stripe 64K ftp://example.com/big.iso -O
---

# `--ftp-mc-stripe`

The stripe size, in bytes, to ask for when --ftp-mc is used: the data of a
transfer is cut into stripes of this size, sent round-robin over the data
connections. The size can be followed by a unit: k or K for kilobytes, M for
megabytes and G for gigabytes. The server may use a smaller size. Without
this option the server's size is used, 4096 bytes by default.
