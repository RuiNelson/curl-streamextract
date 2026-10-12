/***************************************************************************
 *                                  _   _ ____  _
 *  Project                     ___| | | |  _ \| |
 *                             / __| | | | |_) | |
 *                            | (__| |_| |  _ <| |___
 *                             \___|\___/|_| \_\_____|
 *
 * Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
 *
 * This software is licensed as described in the file COPYING, which
 * you should have received as part of this distribution. The terms
 * are also available at https://curl.se/docs/copyright.html.
 *
 * You may opt to use, copy, modify, merge, publish, distribute and/or sell
 * copies of the Software, and permit persons to whom the Software is
 * furnished to do so, under the terms of the COPYING file.
 *
 * This software is distributed on an "AS IS" basis, WITHOUT WARRANTY OF ANY
 * KIND, either express or implied.
 *
 * SPDX-License-Identifier: curl
 *
 ***************************************************************************/
/*
 * libcurl client for the MODE B harness (run_tests.py builds it).
 *
 *   modeb_client info <block|stream> <url>
 *     login only (CURLOPT_NOBODY), print CURLINFO_FTP_TRANSFER_MODE
 *   modeb_client upload <block|stream> <baseurl> <size>...
 *     upload in-memory files of the given sizes with one easy handle,
 *     print per transfer: result, SIZE_UPLOAD_T, the largest upload total
 *     and current values seen by the progress callback
 *   modeb_client abort <block|stream> <url> <size> <abort_after>
 *     upload, the read callback aborts after <abort_after> bytes
 *   (MODEB_PAUSE_MS=n waits n milliseconds between the uploads)
 *   modeb_client download <block|stream> <url>...
 *     download with one easy handle, print result, SIZE_DOWNLOAD_T,
 *     the largest download total and current values seen by the progress
 *     callback, the number of bytes written and a checksum
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif
#include <curl/curl.h>

static void pause_ms(const char *env)
{
  const char *p = getenv(env);
  if(p) {
#ifdef _WIN32
    Sleep((DWORD)atoi(p));
#else
    usleep((useconds_t)atoi(p) * 1000);
#endif
  }
}

struct upload {
  size_t size;
  size_t pos;
  size_t abort_after; /* 0 = never */
};

struct progress {
  curl_off_t dltotal, dlnow, ultotal, ulnow;
};

struct sink {
  size_t len;
  unsigned long sum;
};

static unsigned char pattern(size_t i)
{
  return (unsigned char)((i * 7 + (i >> 8)) & 0xff);
}

static size_t read_cb(char *buf, size_t size, size_t nitems, void *userp)
{
  struct upload *u = userp;
  size_t n = size * nitems;
  size_t i;
  if(u->abort_after && (u->pos >= u->abort_after))
    return CURL_READFUNC_ABORT;
  if(n > u->size - u->pos)
    n = u->size - u->pos;
  if(u->abort_after && (n > u->abort_after - u->pos))
    n = u->abort_after - u->pos;
  for(i = 0; i < n; i++)
    buf[i] = (char)pattern(u->pos + i);
  u->pos += n;
  return n;
}

static size_t write_cb(char *buf, size_t size, size_t nitems, void *userp)
{
  struct sink *s = userp;
  size_t n = size * nitems;
  size_t i;
  for(i = 0; i < n; i++)
    s->sum = (s->sum * 31 + (unsigned char)buf[i]) & 0xffffffffUL;
  s->len += n;
  return n;
}

static int xferinfo_cb(void *p, curl_off_t dltotal, curl_off_t dlnow,
                       curl_off_t ultotal, curl_off_t ulnow)
{
  struct progress *pr = p;
  if(dltotal > pr->dltotal)
    pr->dltotal = dltotal;
  if(dlnow > pr->dlnow)
    pr->dlnow = dlnow;
  if(ultotal > pr->ultotal)
    pr->ultotal = ultotal;
  if(ulnow > pr->ulnow)
    pr->ulnow = ulnow;
  return 0;
}

static CURL *mkhandle(const char *mode)
{
  CURL *curl = curl_easy_init();
  if(!curl)
    exit(2);
  curl_easy_setopt(curl, CURLOPT_FTP_TRANSFER_MODE,
                   strcmp(mode, "block") ? CURLFTPMODE_STREAM :
                   CURLFTPMODE_BLOCK);
  curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);
  if(getenv("MODEB_VERBOSE"))
    curl_easy_setopt(curl, CURLOPT_VERBOSE, 1L);
  if(getenv("MODEB_FTPS")) {
    curl_easy_setopt(curl, CURLOPT_USE_SSL, (long)CURLUSESSL_ALL);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 0L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 0L);
  }
  return curl;
}

static long xfer_mode(CURL *curl)
{
  long mode = -1;
  if(curl_easy_getinfo(curl, CURLINFO_FTP_TRANSFER_MODE, &mode))
    return -2;
  return mode;
}

int main(int argc, char **argv)
{
  CURL *curl;
  int i;

  if(argc < 4) {
    fprintf(stderr, "usage: see source\n");
    return 2;
  }
  curl_global_init(CURL_GLOBAL_ALL);
  curl = mkhandle(argv[2]);

  if(!strcmp(argv[1], "info")) {
    CURLcode result;
    curl_easy_setopt(curl, CURLOPT_URL, argv[3]);
    curl_easy_setopt(curl, CURLOPT_NOBODY, 1L);
    result = curl_easy_perform(curl);
    printf("result=%d mode=%ld\n", (int)result, xfer_mode(curl));
  }
  else if(!strcmp(argv[1], "upload") || !strcmp(argv[1], "abort")) {
    int abort_mode = !strcmp(argv[1], "abort");
    int last = abort_mode ? 5 : argc;
    for(i = 4; i < last && i < argc; i++) {
      struct upload u;
      struct progress pr;
      char url[512];
      CURLcode result;
      curl_off_t ul = -1;
      memset(&u, 0, sizeof(u));
      memset(&pr, 0, sizeof(pr));
      u.size = (size_t)strtoul(argv[i], NULL, 10);
      if(abort_mode && (argc > 5))
        u.abort_after = (size_t)strtoul(argv[5], NULL, 10);
      if(abort_mode)
        snprintf(url, sizeof(url), "%s", argv[3]);
      else
        snprintf(url, sizeof(url), "%sup%d", argv[3], i - 4);
      curl_easy_setopt(curl, CURLOPT_URL, url);
      curl_easy_setopt(curl, CURLOPT_UPLOAD, 1L);
      curl_easy_setopt(curl, CURLOPT_READFUNCTION, read_cb);
      curl_easy_setopt(curl, CURLOPT_READDATA, &u);
      curl_easy_setopt(curl, CURLOPT_INFILESIZE_LARGE, (curl_off_t)u.size);
      curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
      curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, xferinfo_cb);
      curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &pr);
      if(i > 4)
        pause_ms("MODEB_PAUSE_MS");
      result = curl_easy_perform(curl);
      curl_easy_getinfo(curl, CURLINFO_SIZE_UPLOAD_T, &ul);
      printf("result=%d size_upload=%" CURL_FORMAT_CURL_OFF_T
             " ultotal=%" CURL_FORMAT_CURL_OFF_T
             " ulnow=%" CURL_FORMAT_CURL_OFF_T " mode=%ld\n",
             (int)result, ul, pr.ultotal, pr.ulnow, xfer_mode(curl));
    }
  }
  else if(!strcmp(argv[1], "download")) {
    for(i = 3; i < argc; i++) {
      struct sink s;
      struct progress pr;
      CURLcode result;
      curl_off_t dl = -1;
      memset(&s, 0, sizeof(s));
      memset(&pr, 0, sizeof(pr));
      curl_easy_setopt(curl, CURLOPT_URL, argv[i]);
      curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_cb);
      curl_easy_setopt(curl, CURLOPT_WRITEDATA, &s);
      curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
      curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, xferinfo_cb);
      curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &pr);
      result = curl_easy_perform(curl);
      curl_easy_getinfo(curl, CURLINFO_SIZE_DOWNLOAD_T, &dl);
      printf("result=%d size_download=%" CURL_FORMAT_CURL_OFF_T
             " dltotal=%" CURL_FORMAT_CURL_OFF_T
             " dlnow=%" CURL_FORMAT_CURL_OFF_T
             " written=%lu sum=%lu mode=%ld\n",
             (int)result, dl, pr.dltotal, pr.dlnow,
             (unsigned long)s.len, s.sum, xfer_mode(curl));
    }
  }
  curl_easy_cleanup(curl);
  curl_global_cleanup();
  return 0;
}
