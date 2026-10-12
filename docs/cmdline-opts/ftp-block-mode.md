---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Long: ftp-block-mode
Help: Use FTP block mode (MODE B)
Protocols: FTP
Added: 8.23.0
Category: ftp
Multi: boolean
See-also:
  - ftp-pasv
  - ftp-port
Example:
  - --ftp-block-mode -T "{one,two,three}.txt" ftp://example.com/
---

# `--ftp-block-mode`

Ask the FTP server for block mode (MODE B) once logged in. If the server
accepts it, the end of each file is a flag in the data stream instead of the
closing of the data connection, so curl keeps the data connection open and
uses it for the next transfer on the same control connection, without a new
PASV, EPSV, PORT or EPRT command or a new TLS handshake. A data connection
that closes before the end of file makes the transfer fail.

If the server refuses block mode, curl uses the default stream mode.
