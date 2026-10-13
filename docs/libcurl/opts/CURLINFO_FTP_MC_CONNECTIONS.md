---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Title: CURLINFO_FTP_MC_CONNECTIONS
Section: 3
Source: libcurl
See-also:
  - CURLOPT_FTP_MC_CONNECTIONS (3)
  - curl_easy_getinfo (3)
  - curl_easy_setopt (3)
Protocol:
  - FTP
Added-in: 8.23.0
---

# NAME

CURLINFO_FTP_MC_CONNECTIONS - number of FTP data connections used

# SYNOPSIS

~~~c
#include <curl/curl.h>

CURLcode curl_easy_getinfo(CURL *handle, CURLINFO_FTP_MC_CONNECTIONS,
                           long *count);
~~~

# DESCRIPTION

Pass a pointer to a long to receive the number of data connections that the
most recent transfer used in parallel with FTPMC (see
CURLOPT_FTP_MC_CONNECTIONS(3)). It is 0 when the transfer did not use FTPMC:
when it was not asked for, when the server does not support it or refused
it, or when the transfer was not an FTP transfer with data.

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
    if(result == CURLE_OK) {
      long count;
      result = curl_easy_getinfo(curl, CURLINFO_FTP_MC_CONNECTIONS, &count);
      if(!result)
        printf("Data connections: %ld\n", count);
    }
    curl_easy_cleanup(curl);
  }
}
~~~

# %AVAILABILITY%

# RETURN VALUE

curl_easy_getinfo(3) returns a CURLcode indicating success or error.

CURLE_OK (0) means everything was OK, non-zero means an error occurred, see
libcurl-errors(3).
