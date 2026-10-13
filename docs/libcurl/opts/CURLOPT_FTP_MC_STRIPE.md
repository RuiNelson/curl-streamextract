---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Title: CURLOPT_FTP_MC_STRIPE
Section: 3
Source: libcurl
See-also:
  - CURLOPT_FTP_MC_CONNECTIONS (3)
Protocol:
  - FTP
Added-in: 8.23.0
---

# NAME

CURLOPT_FTP_MC_STRIPE - FTPMC stripe size

# SYNOPSIS

~~~c
#include <curl/curl.h>

CURLcode curl_easy_setopt(CURL *handle, CURLOPT_FTP_MC_STRIPE, long size);
~~~

# DESCRIPTION

Pass a long with the stripe size in bytes, from 1 to 4294967295, to ask for
when libcurl uses several FTP data connections (CURLOPT_FTP_MC_CONNECTIONS(3)).
The data stream of a transfer is cut into stripes of this size and the
stripes go round-robin over the data connections.

0 asks for no particular size: the server uses its current one, 4096 bytes by
default. The server may lower the size, for example to the largest one it
supports, and libcurl uses the size of its reply.

Larger stripes mean fewer, larger reads and writes on each connection, but
files shorter than the number of connections times the stripe size do not use
all connections. libcurl buffers at least two stripes for each connection.

# DEFAULT

0

# %PROTOCOLS%

# EXAMPLE

~~~c
int main(void)
{
  CURL *curl = curl_easy_init();
  if(curl) {
    CURLcode result;
    curl_easy_setopt(curl, CURLOPT_URL, "ftp://example.com/big.iso");
    curl_easy_setopt(curl, CURLOPT_FTP_MC_CONNECTIONS, 4L);
    curl_easy_setopt(curl, CURLOPT_FTP_MC_STRIPE, 65536L);
    result = curl_easy_perform(curl);
    curl_easy_cleanup(curl);
  }
}
~~~

# %AVAILABILITY%

# RETURN VALUE

curl_easy_setopt(3) returns a CURLcode indicating success or error.

CURLE_OK (0) means everything was OK, non-zero means an error occurred, see
libcurl-errors(3).
