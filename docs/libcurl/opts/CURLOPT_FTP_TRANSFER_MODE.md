---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Title: CURLOPT_FTP_TRANSFER_MODE
Section: 3
Source: libcurl
See-also:
  - CURLINFO_FTP_TRANSFER_MODE (3)
  - CURLOPT_FTPPORT (3)
  - CURLOPT_FTP_USE_EPSV (3)
Protocol:
  - FTP
Added-in: 8.23.0
---

# NAME

CURLOPT_FTP_TRANSFER_MODE - FTP transfer mode

# SYNOPSIS

~~~c
#include <curl/curl.h>

CURLcode curl_easy_setopt(CURL *handle, CURLOPT_FTP_TRANSFER_MODE,
                          long mode);
~~~

# DESCRIPTION

Pass a long telling libcurl which FTP transfer mode (RFC 959 section 3.4) to
use for the data connection.

## CURLFTPMODE_STREAM

Stream mode, the default. libcurl never sends a MODE command. The end of each
file is marked by closing the data connection, so every transfer sets up a new
data connection.

## CURLFTPMODE_BLOCK

Block mode. Once logged in, libcurl sends MODE B on the control connection,
once. If the server accepts it with a 200 reply, the data of every transfer
is sent in blocks, with the end of file marked by a flag in the data stream
instead of by closing the connection. After a transfer that succeeded and that
the server confirmed with a 250 reply, libcurl keeps the data connection open
and the next transfer on the same control connection uses it directly,
without a new PASV, EPSV, PORT or EPRT command, a new TCP connection or a new
TLS handshake. This makes many small transfers over one connection much
faster.

If the server answers MODE B with anything else than 200, libcurl uses stream
mode on that connection and does not ask again. CURLINFO_FTP_TRANSFER_MODE(3)
tells which mode is in use.

In block mode, a data connection that closes before the end of file flag
makes the transfer fail, so truncated transfers are detected. The byte counts,
size checks and progress information only include the file data, not the
block headers.

A connection that uses block mode is not reused by a transfer that asks for
stream mode.

# DEFAULT

CURLFTPMODE_STREAM

# %PROTOCOLS%

# EXAMPLE

~~~c
int main(void)
{
  CURL *curl = curl_easy_init();
  if(curl) {
    CURLcode result;
    long mode;
    curl_easy_setopt(curl, CURLOPT_URL, "ftp://example.com/file.txt");
    curl_easy_setopt(curl, CURLOPT_FTP_TRANSFER_MODE, CURLFTPMODE_BLOCK);
    result = curl_easy_perform(curl);
    if(!result &&
       !curl_easy_getinfo(curl, CURLINFO_FTP_TRANSFER_MODE, &mode) &&
       (mode != CURLFTPMODE_BLOCK))
      printf("The server does not support block mode\n");
    curl_easy_cleanup(curl);
  }
}
~~~

# %AVAILABILITY%

# RETURN VALUE

curl_easy_setopt(3) returns a CURLcode indicating success or error.

CURLE_OK (0) means everything was OK, non-zero means an error occurred, see
libcurl-errors(3).
