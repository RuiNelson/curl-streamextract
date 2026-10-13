---
c: Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
SPDX-License-Identifier: curl
Title: CURLINFO_FTP_TRANSFER_MODE
Section: 3
Source: libcurl
See-also:
  - CURLOPT_FTP_TRANSFER_MODE (3)
  - curl_easy_getinfo (3)
  - curl_easy_setopt (3)
Protocol:
  - FTP
Added-in: 8.23.0
---

# NAME

CURLINFO_FTP_TRANSFER_MODE - FTP transfer mode in use

# SYNOPSIS

~~~c
#include <curl/curl.h>

CURLcode curl_easy_getinfo(CURL *handle, CURLINFO_FTP_TRANSFER_MODE,
                           long *mode);
~~~

# DESCRIPTION

Pass a pointer to a long to receive the FTP transfer mode in effect on the
control connection used by the most recent transfer: CURLFTPMODE_BLOCK when
the server accepted block mode (see CURLOPT_FTP_TRANSFER_MODE(3)), otherwise
CURLFTPMODE_STREAM.

Block mode is asked for right after logging in, so the mode is known even
after a transfer that only logged in. The value is 0 (CURLFTPMODE_STREAM) when
the most recent transfer did not use FTP or when it is not known.

# %PROTOCOLS%

# EXAMPLE

~~~c
int main(void)
{
  CURL *curl = curl_easy_init();
  if(curl) {
    CURLcode result;
    curl_easy_setopt(curl, CURLOPT_URL, "ftp://example.com/");
    curl_easy_setopt(curl, CURLOPT_FTP_TRANSFER_MODE, CURLFTPMODE_BLOCK);
    curl_easy_setopt(curl, CURLOPT_NOBODY, 1L);
    result = curl_easy_perform(curl);
    if(result == CURLE_OK) {
      long mode;
      result = curl_easy_getinfo(curl, CURLINFO_FTP_TRANSFER_MODE, &mode);
      if(!result)
        printf("Block mode: %s\n",
               (mode == CURLFTPMODE_BLOCK) ? "yes" : "no");
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
