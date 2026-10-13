---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Title: CURLOPT_FTP_MC_CONNECTIONS
Section: 3
Source: libcurl
See-also:
  - CURLINFO_FTP_MC_CONNECTIONS (3)
  - CURLOPT_FTP_MC_STRIPE (3)
  - CURLOPT_FTP_TRANSFER_MODE (3)
Protocol:
  - FTP
Added-in: 8.23.0
---

# NAME

CURLOPT_FTP_MC_CONNECTIONS - number of parallel FTP data connections

# SYNOPSIS

~~~c
#include <curl/curl.h>

CURLcode curl_easy_setopt(CURL *handle, CURLOPT_FTP_MC_CONNECTIONS,
                          long count);
~~~

# DESCRIPTION

Pass a long with the number of TCP data connections, from 1 to 64, that each
FTP transfer should use in parallel, with the FTPMC extension
(draft-ftpmc-00). 0 disables it.

A single TCP connection often cannot use the whole capacity of a path, for
example over Wi-Fi or on paths with a high bandwidth-delay product. With
FTPMC the data of each transfer is cut into stripes that are sent round-robin
over the connections, stripe i on connection i mod N, without any header.

libcurl asks the server with FEAT whether it supports FTPMC, once per control
connection. If it lists MC, libcurl sends OPTS MC with the number of
connections, lowered to the largest the server announces, and the stripe size
of CURLOPT_FTP_MC_STRIPE(3). The server may lower both: libcurl uses the
values in its reply. Then MPSV replaces EPSV or PASV and libcurl connects to
all the ports in the reply. Each transfer still sees a single data stream, so
all byte counts, size checks and progress information are unchanged.

If the server does not support FTPMC, refuses OPTS MC or answers MPSV with
anything else than 224, the transfer uses a single data connection. FTPMC is
not used for active mode (CURLOPT_FTPPORT(3)), with CURLOPT_FTP_USE_PRET(3)
or through a proxy.

In stream mode, each transfer uses a new set of connections. In block mode
(CURLOPT_FTP_TRANSFER_MODE(3)) the set is kept open after a transfer that
succeeded and the next transfer on the same control connection uses it,
without a new MPSV or new connections.

When a data connection ends early, the stripes that follow are missing: the
transfer fails with CURLE_PARTIAL_FILE.

With data protection (FTPS with PROT P), each data connection has its own TLS
session.

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
