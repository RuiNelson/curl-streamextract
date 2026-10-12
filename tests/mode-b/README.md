<!--
Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.

SPDX-License-Identifier: curl
-->

# FTP block mode tests

Tests for FTP block mode (`MODE B`, RFC 959 section 3.4.2) with a kept and
reused data connection: `CURLOPT_FTP_TRANSFER_MODE`,
`CURLINFO_FTP_TRANSFER_MODE` and the `--ftp-block-mode` tool option.

- `modeb_server.py` is a small FTP server (Python 3 standard library) that
  implements block mode as the client expects it: `200` to `MODE B`, `125`
  when a transfer command reuses the kept data connection, `250` after a
  successful transfer (the data connection stays open) and `426` when the
  data connection closes before the end of file block. It can inject faults:
  refusing `MODE B`, `425` on reuse, `226` instead of `250`, truncated data,
  invalid descriptors, restart markers, headers split across writes, bytes
  after the end of file, closing an idle kept connection and slow reading.
  It supports explicit (`AUTH TLS`) and implicit FTPS, with `PROT P`.
- `modeb_client.c` is a libcurl program for what the tool cannot show: the
  info value, payload-only byte counts and progress, and a read callback that
  aborts an upload.
- `run_tests.py` runs the server in process, drives the curl tool and the
  libcurl program, and checks the files, the commands the server got (one
  `EPSV`/`PASV`/`EPRT`/`PORT` for many transfers) and the data connection
  events.

Run, with a CMake build of this curl (shared libcurl, for the libcurl
program):

    python3 tests/mode-b/run_tests.py --build <build dir> [-k NAME] [-v]

The FTPS tests need the `openssl` command line tool to make a self-signed
certificate. The libcurl program is compiled with `$CC` or `cc`.

The curl test suite also has block mode cases (tests 3900 to 3907) that use
`ftpserver.pl` with `REPLY MODE 200` and `STORBLOCK`: as that server always
closes the data connection after a transfer, they check the framing, the
fallback to stream mode and the errors, not the reuse.
