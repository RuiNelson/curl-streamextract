---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Long: ftp-mc
Arg: <num>
Help: Use <num> parallel FTP data connections (FTPMC)
Protocols: FTP
Added: 8.23.0
Category: ftp
Multi: single
See-also:
  - ftp-mc-stripe
  - ftp-block-mode
Example:
  - --ftp-mc 4 ftp://example.com/big.iso -O
  - --ftp-mc 4 -T big.iso ftp://example.com/
---

# `--ftp-mc`

Carry each FTP transfer over <num> TCP data connections in parallel, from 1
to 64, with the FTPMC extension (draft-ftpmc-00). The data is cut into stripes
that are sent round-robin over the connections. This can make a transfer
much faster on paths where a single TCP connection cannot use the whole
capacity, like Wi-Fi. 0 disables it.

curl asks the server with FEAT whether it supports FTPMC. If it does, curl
sets the number of connections with OPTS MC (the server may lower it) and uses
MPSV instead of EPSV or PASV. If the server does not support FTPMC or refuses
it, curl uses one data connection. FTPMC is not used with --ftp-port or
through a proxy.

With --ftp-block-mode the connections are kept open between the transfers on
the same control connection.
