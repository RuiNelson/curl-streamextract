#ifndef HEADER_CURL_FTP_INT_H
#define HEADER_CURL_FTP_INT_H
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
#include "curl_setup.h"

#include "pingpong.h"
#include "ftp.h"

#ifndef CURL_DISABLE_FTP

/****************************************************************************
 * FTP unique setup
 ***************************************************************************/
enum {
  FTP_STOP,    /* do nothing state, stops the state machine */
  FTP_WAIT220, /* waiting for the initial 220 response immediately after
                  a connect */
  FTP_AUTH,
  FTP_USER,
  FTP_PASS,
  FTP_ACCT,
  FTP_PBSZ,
  FTP_PROT,
  FTP_CCC,
  FTP_PWD,
  FTP_SYST,
  FTP_NAMEFMT,
  FTP_MODE, /* MODE B at the end of the connect phase */
  FTP_MODE_XFER, /* MODE B before setting up a data connection */
  FTP_MC_FEAT, /* FEAT, to learn if the server supports FTPMC */
  FTP_MC_OPTS, /* OPTS MC, to set the FTPMC connections and stripe size */
  FTP_QUOTE, /* waiting for a response to a command sent in a quote list */
  FTP_RETR_PREQUOTE,
  FTP_STOR_PREQUOTE,
  FTP_LIST_PREQUOTE,
  FTP_POSTQUOTE,
  FTP_CWD,  /* change directory */
  FTP_MKD,  /* if the directory did not exist */
  FTP_MDTM, /* to figure out the datestamp */
  FTP_TYPE, /* to set type when doing a head-like request */
  FTP_LIST_TYPE, /* set type when about to do a directory list */
  FTP_RETR_LIST_TYPE,
  FTP_RETR_TYPE, /* set type when about to RETR a file */
  FTP_STOR_TYPE, /* set type when about to STOR a file */
  FTP_SIZE, /* get the remote file's size for head-like request */
  FTP_RETR_SIZE, /* get the remote file's size for RETR */
  FTP_STOR_SIZE, /* get the size for STOR */
  FTP_REST, /* when used to check if the server supports it in head-like */
  FTP_RETR_REST, /* when asking for "resume" in for RETR */
  FTP_PORT, /* generic state for PORT, LPRT and EPRT, check count1 */
  FTP_PRET, /* generic state for PRET RETR, PRET STOR and PRET LIST/NLST */
  FTP_PASV, /* generic state for PASV and EPSV, check count1 */
  FTP_MPSV, /* FTPMC: MPSV, the passive ports of a connection set */
  FTP_LIST, /* generic state for LIST, NLST or a custom list command */
  FTP_RETR,
  FTP_STOR, /* generic state for STOR and APPE */
  FTP_QUIT,
  FTP_LAST  /* never used */
};
typedef unsigned char ftpstate; /* use the enum values */

struct ftp_parselist_data; /* defined later in ftplistparser.c */

struct ftp_wc {
  struct ftp_parselist_data *parser;
};

/* This FTP struct is used in the Curl_easy. All FTP data that is
   connection-oriented must be in FTP_conn to properly deal with the fact that
   perhaps the Curl_easy is changed between the times the connection is
   used. */
struct FTP {
  char *path;    /* points to the urlpieces struct field */
  char *pathalloc; /* if non-NULL a pointer to an allocated path */

  /* transfer a file/body or not, done as a typedefed enum to make debuggers
     display the full symbol and not the numerical value */
  curl_pp_transfer transfer;
  curl_off_t downloadsize;
};

/* ftp_conn->blk_mode values: the result of asking for block mode */
#define FTP_BLK_UNKNOWN 0 /* MODE B not sent on this connection */
#define FTP_BLK_ON      1 /* server accepted MODE B */
#define FTP_BLK_OFF     2 /* server refused MODE B, stream mode */

/* ftp_conn->mc_state values: what the server said about FTPMC */
#define FTP_MC_UNKNOWN 0 /* FEAT not sent on this connection */
#define FTP_MC_NONE    1 /* the server does not support FTPMC */
#define FTP_MC_AVAIL   2 /* supported, not enabled (or OPTS MC refused) */
#define FTP_MC_ON      3 /* enabled with mc_n connections, mc_stripe */

struct cf_ftp_mc_ctx;

/* one struct entry for each path component (of 'rawpath') */
struct pathcomp {
  int start; /* start column */
  int len;   /* length in bytes */
};

/* ftp_conn is used for struct connection-oriented data in the connectdata
   struct */
struct ftp_conn {
  struct pingpong pp;
  char *account;
  char *alternative_to_user;
  char *entrypath; /* the PWD reply when we logged on */
  const char *file; /* URL-decoded filename (or path), points into rawpath */
  char *rawpath; /* URL decoded, allocated, version of the path */
  struct pathcomp *dirs; /* allocated array for path components */
  char *prevpath;   /* URL-decoded conn->path from the previous transfer */
  char transfertype; /* set by ftp_transfertype for use by Curl_client_write()a
                        and others (A/I or zero) */
  char *server_os;     /* The target server operating system. */
  char *blk_kept_port; /* CURLOPT_FTPPORT of the kept data connection */
  struct cf_ftp_mc_ctx *mc_pend; /* connection set being connected */
  curl_off_t known_filesize; /* file size is different from -1, if wildcard
                                LIST parsing was done and wc_statemach set
                                it */
  int count1; /* general purpose counter for the state machine */
  int count2; /* general purpose counter for the state machine */
  int count3; /* general purpose counter for the state machine */
  unsigned short dirdepth;  /* number of entries used in the 'dirs' array,
                               < FTP_MAX_DIR_DEPTH */
  unsigned short cwdcount;  /* number of CWD commands issued,
                               < FTP_MAX_DIR_DEPTH */
  unsigned char state; /* (ftpstate enum) always use ftp.c:state() to change
                          state! */
  unsigned char use_ssl;   /* if AUTH TLS is to be attempted etc, for FTP or
                              IMAP or POP3 or others! (type: curl_usessl)*/
  unsigned char ccc;       /* ccc level for this connection */
  unsigned char blk_want;  /* CURLOPT_FTP_TRANSFER_MODE when created */
  unsigned char blk_mode;  /* FTP_BLK_* */
  unsigned char blk_retry; /* transfer command state to send again on a new
                              data connection after a 425, or 0 */
  unsigned char blk_kept_ipver; /* CURLOPT_IPRESOLVE of the kept data conn */
  unsigned char mc_state; /* FTP_MC_* */
  unsigned char mc_max;   /* the largest N the server accepts (FEAT) */
  unsigned char mc_n;     /* connections in effect (OPTS MC reply) */
  unsigned char mc_want_n; /* connections asked for with OPTS MC */
  unsigned char mc_next;  /* index of the connection being connected */
  uint32_t mc_stripe;     /* stripe size in effect (OPTS MC reply) */
  uint32_t mc_want_stripe; /* stripe size asked for with OPTS MC */
  unsigned short mc_ports[CURL_FTP_MC_MAX_CONNECTIONS]; /* MPSV reply */
  BIT(blk_kept);    /* SECONDARYSOCKET is a kept block mode data connection */
  BIT(blk_kept_active); /* the kept data connection was made with PORT */
  BIT(blk_kept_ssl);    /* the kept data connection uses TLS */
  BIT(blk_reused);  /* the current transfer reuses the kept connection */
  BIT(blk_append);  /* the current upload command is APPE */
  BIT(ftp_trying_alternative);
  BIT(dont_check);  /* Set to TRUE to prevent the final (post-transfer)
                       file size and 226/250 status check. It should still
                       read the line, ignore the result. */
  BIT(ctl_valid);   /* Tells Curl_ftp_quit() whether or not to do anything. If
                       the connection has timed out or been closed, this
                       should be FALSE when it gets to Curl_ftp_quit() */
  BIT(cwddone);     /* if it has been determined that the proper CWD combo
                       already has been done */
  BIT(cwdfail);     /* set TRUE if a CWD command fails, as then we must prevent
                       caching the current directory */
  BIT(wait_data_conn); /* this is set TRUE if data connection is waited */
  BIT(shutdown);    /* connection is being shutdown, e.g. QUIT */
};

/* meta key for storing `struct FTP` as easy meta data */
#define CURL_META_FTP_EASY   "meta:proto:ftp:easy"
/* meta key for storing `struct ftp_conn` as connection meta data */
#define CURL_META_FTP_CONN   "meta:proto:ftp:conn"

#endif /* CURL_DISABLE_FTP */

#endif /* HEADER_CURL_FTP_INT_H */
