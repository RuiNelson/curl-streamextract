#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#***************************************************************************
#                                  _   _ ____  _
#  Project                     ___| | | |  _ \| |
#                             / __| | | | |_) | |
#                            | (__| |_| |  _ <| |___
#                             \___|\___/|_| \_\_____|
#
# Copyright (C) Daniel Stenberg, <daniel@haxx.se>, et al.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://curl.se/docs/copyright.html.
#
# You may opt to use, copy, modify, merge, publish, distribute and/or sell
# copies of the Software, and permit persons to whom the Software is
# furnished to do so, under the terms of the COPYING file.
#
# This software is distributed on an "AS IS" basis, WITHOUT WARRANTY OF ANY
# KIND, either express or implied.
#
# SPDX-License-Identifier: curl
#
###########################################################################
"""Tests for FTP block mode (CURLOPT_FTP_TRANSFER_MODE, --ftp-block-mode)
against modeb_server.py, driving the curl tool and a small libcurl client.

  python3 run_tests.py --build <cmake build dir> [-k NAME] [-v]

The build directory must contain src/curl and the libcurl library (lib/).
The libcurl client (modeb_client.c) is compiled with the C compiler found
as $CC or 'cc'. FTPS tests need the openssl command line tool.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modeb_server  # noqa: E402

SIZES = [0, 1, 65535, 65536, 65537, 3 * 1024 * 1024 + 12345]


class Failure(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Failure(msg)


def pattern(size):
    """The bytes modeb_client uploads for a given size."""
    return bytes(((i * 7 + (i >> 8)) & 0xff) for i in range(size))


def csum(data):
    s = 0
    for b in data:
        s = (s * 31 + b) & 0xffffffff
    return s


class Env:
    def __init__(self, args):
        self.build = os.path.abspath(args.build)
        self.verbose = args.verbose
        self.curl = os.path.join(self.build, 'src', 'curl')
        check(os.path.exists(self.curl), 'no curl tool in %s' % self.curl)
        self.tmp = tempfile.mkdtemp(prefix='modeb-')
        self.client = self.build_client()
        self.tls_ctx = self.make_tls()

    def build_client(self):
        libdir = os.path.join(self.build, 'lib')
        lib = None
        for name in ('libcurl.dylib', 'libcurl-d.dylib', 'libcurl.so',
                     'libcurl-d.so'):
            if os.path.exists(os.path.join(libdir, name)):
                lib = os.path.join(libdir, name)
                break
        if not lib:
            print('no shared libcurl in %s, libcurl tests skipped' % libdir)
            return None
        out = os.path.join(self.tmp, 'modeb_client')
        cc = os.environ.get('CC', 'cc')
        inc = os.path.join(HERE, '..', '..', 'include')
        cmd = [cc, '-o', out, os.path.join(HERE, 'modeb_client.c'),
               '-I', inc, lib, '-Wl,-rpath,' + libdir]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print('cannot build modeb_client: %s' % r.stderr)
            return None
        return out

    def make_tls(self):
        openssl = shutil.which('openssl')
        if not openssl:
            return None
        import ssl
        key = os.path.join(self.tmp, 'key.pem')
        crt = os.path.join(self.tmp, 'cert.pem')
        r = subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048',
                            '-nodes', '-keyout', key, '-out', crt,
                            '-days', '2', '-subj', '/CN=localhost'],
                           capture_output=True)
        if r.returncode:
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(crt, key)
        return ctx

    def server(self, **cfg):
        root = tempfile.mkdtemp(dir=self.tmp)
        srv = modeb_server.Server(root)
        for k, v in cfg.items():
            check(hasattr(srv.cfg, k), 'bad config %s' % k)
            setattr(srv.cfg, k, v)
        srv.cfg.tls_ctx = self.tls_ctx
        return srv

    def file(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def run_curl(self, args, expect=0):
        cmd = [self.curl, '-sS', '--max-time', '60'] + args
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if self.verbose:
            print('$ %s -> %d' % (' '.join(cmd), r.returncode))
            sys.stdout.write(r.stderr.decode('latin-1'))
        check(r.returncode == expect,
              'curl exit %d, expected %d: %s' %
              (r.returncode, expect, r.stderr.decode('latin-1')[-800:]))
        return r

    def run_client(self, args, env=None):
        if not self.client:
            raise Skip('no libcurl client')
        e = dict(os.environ)
        if env:
            e.update(env)
        r = subprocess.run([self.client] + args, capture_output=True,
                           text=True, timeout=120, env=e)
        if self.verbose:
            print('$ client %s' % ' '.join(args))
            sys.stdout.write(r.stdout + r.stderr)
        check(r.returncode == 0, 'client failed: %s' % r.stderr[-800:])
        lines = []
        for line in r.stdout.splitlines():
            if not line.startswith('result='):
                continue
            d = {}
            for kv in line.split():
                k, _, v = kv.partition('=')
                d[k] = int(v)
            lines.append(d)
        return lines


class Skip(Exception):
    pass


def ops(*groups):
    """curl tool arguments for several operations (--next) on the same
    connection, each with --ftp-block-mode. -T files pair with the URLs of
    their operation in order, other options apply to the whole operation."""
    args = []
    for g in groups:
        if args:
            args.append('--next')
        args += ['--ftp-block-mode'] + list(g)
    return args


def url(srv, path=''):
    return 'ftp://127.0.0.1:%d/%s' % (srv.port, path)


def upload_args(env, srv, sizes, prefix='f'):
    args = []
    files = {}
    for i, size in enumerate(sizes):
        name = '%s%d' % (prefix, i)
        data = os.urandom(size)
        files[name] = data
        args += ['-T', env.file(name, data), url(srv, name)]
    return args, files


def check_files(srv, files):
    for name, data in files.items():
        path = os.path.join(srv.root, name)
        check(os.path.exists(path), 'missing %s on server' % name)
        with open(path, 'rb') as f:
            got = f.read()
        check(got == data, '%s differs: %d bytes, expected %d' %
              (name, len(got), len(data)))


def data_setups(srv):
    return sum(srv.count(c) for c in ('EPSV', 'PASV', 'EPRT', 'PORT'))


# --- tests -------------------------------------------------------------

def test_upload_many(env):
    """N uploads on one connection: one EPSV, byte-identical files"""
    srv = env.server()
    args, files = upload_args(env, srv, SIZES)
    env.run_curl(['--ftp-block-mode'] + args)
    check_files(srv, files)
    check(srv.count('MODE') == 1, 'MODE sent %d times' % srv.count('MODE'))
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))
    check(srv.events.count('new-data-conn') == 1, srv.events)
    check(srv.events.count('reuse') == len(SIZES) - 1, srv.events)
    check(srv.events.count('upload-eof') == len(SIZES), srv.events)
    # MODE B right after login, before anything else
    i = srv.log.index('MODE B')
    check(srv.log[i - 1] == 'PWD', 'MODE B not after PWD: %s' % srv.log)


def test_upload_slow_reader(env):
    """partial sends to a slow server, plain and TLS"""
    for tls in ([], ['--ssl-reqd', '-k']):
        if tls and not env.tls_ctx:
            continue
        srv = env.server(slow_read=True)
        args, files = upload_args(env, srv, [4 * 1024 * 1024 + 3, 70000, 1])
        env.run_curl(['--ftp-block-mode'] + tls + args)
        check_files(srv, files)
        check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_upload_small_sends(env):
    """many short sends (CURL_SMALLSENDS, debug builds)"""
    srv = env.server()
    args, files = upload_args(env, srv, [0, 1, 65537, 200000])
    os.environ['CURL_SMALLSENDS'] = '1000'
    try:
        env.run_curl(['--ftp-block-mode'] + args)
    finally:
        del os.environ['CURL_SMALLSENDS']
    check_files(srv, files)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_many_small(env):
    """300 small uploads (plain and TLS) on one data connection"""
    for tls in ([], ['--ssl-reqd', '-k']):
        if tls and not env.tls_ctx:
            continue
        srv = env.server()
        d = os.path.join(env.tmp, 'many')
        os.makedirs(d, exist_ok=True)
        files = {}
        for i in range(1, 301):
            data = os.urandom(i * 3)
            files['m%d' % i] = data
            with open(os.path.join(d, 'm%d' % i), 'wb') as f:
                f.write(data)
        env.run_curl(['--ftp-block-mode'] + tls +
                     ['-T', os.path.join(d, 'm[1-300]'), url(srv)])
        check_files(srv, files)
        check(srv.count('STOR') == 300, 'STOR count %d' % srv.count('STOR'))
        check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_upload_counts(env):
    """payload-only upload byte counts, progress and INFILESIZE check"""
    srv = env.server()
    out = env.run_client(['upload', 'block', url(srv)] +
                         [str(s) for s in SIZES])
    check(len(out) == len(SIZES), out)
    for size, o in zip(SIZES, out):
        check(o['result'] == 0, o)
        check(o['size_upload'] == size, o)
        check(o['ultotal'] == size, o)
        check(o['ulnow'] == size, o)
        check(o['mode'] == 1, o)
    check_files(srv, dict(('up%d' % i, pattern(s))
                          for i, s in enumerate(SIZES)))
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_append_resume(env):
    """APPE (--append) and resumed upload (-C -) on the kept connection"""
    srv = env.server()
    a = os.urandom(70000)
    b = os.urandom(5000)
    full = os.urandom(200000)
    with open(os.path.join(srv.root, 'resume'), 'wb') as f:
        f.write(full[:123457])
    env.run_curl(ops(['-T', env.file('a', a), url(srv, 'app')],
                     ['-a', '-T', env.file('b', b), url(srv, 'app')],
                     ['-C', '-', '-T', env.file('full', full),
                      url(srv, 'resume')]))
    check_files(srv, {'app': a + b, 'resume': full})
    check(srv.count('APPE') == 2, srv.log)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def download(env, srv, extra=None):
    names = sorted(srv.cfg.files)
    args = list(extra or [])
    outs = {}
    for n in names:
        outs[n] = os.path.join(env.tmp, 'dl-' + n)
        args += [url(srv, n), '-o', outs[n]]
    lst = os.path.join(env.tmp, 'dl-list')
    nlst = os.path.join(env.tmp, 'dl-nlst')
    args += [url(srv), '-o', lst]
    for p in list(outs.values()) + [lst, nlst]:
        if os.path.exists(p):
            os.unlink(p)
    env.run_curl(ops(args, ['-l', url(srv), '-o', nlst]))
    for n in names:
        if not os.path.exists(outs[n]):
            check(srv.cfg.files[n] == b'', '%s not downloaded' % n)
            continue
        with open(outs[n], 'rb') as f:
            got = f.read()
        check(got == srv.cfg.files[n], '%s: %d bytes, expected %d' %
              (n, len(got), len(srv.cfg.files[n])))
    want = srv.cfg.listing.replace(b'\r\n', b'\n')
    for p in (lst, nlst):
        with open(p, 'rb') as f:
            got = f.read()
        check(got in (want, srv.cfg.listing), 'listing: %r' % got)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def dl_files():
    return {'d0': b'', 'd1': b'x', 'd2': os.urandom(65535),
            'd3': os.urandom(65536), 'd4': os.urandom(1024 * 1024 + 7),
            'text': b'one\r\ntwo\r\nthree'}


LISTING = b'-rw-r--r-- 1 ftp ftp 3 Jan 1 2026 a\r\nsecond line\r\n'


def test_download(env):
    """RETR/LIST/NLST decoding, separate EOF block"""
    download(env, env.server(files=dl_files(), listing=LISTING))


def test_download_eof_on_data(env):
    """RETR/LIST decoding with EOF on the last data block"""
    download(env, env.server(files=dl_files(), listing=LISTING,
                             eof_on_data=True))


def test_download_split(env):
    """headers and payloads split across reads (one byte per write)"""
    files = {'s0': b'', 's1': b'ab', 's2': os.urandom(3000)}
    download(env, env.server(files=files, listing=LISTING, block_size=7,
                             split_writes=True))
    download(env, env.server(files=files, listing=LISTING, block_size=5,
                             split_writes=True, eof_on_data=True))


def test_download_restart_marker(env):
    """a restart marker block is not file data"""
    download(env, env.server(files=dl_files(), listing=LISTING,
                             restart_marker=True))


def test_download_counts(env):
    """payload-only download byte counts and progress"""
    files = dl_files()
    srv = env.server(files=files)
    names = sorted(files)
    out = env.run_client(['download', 'block'] +
                         [url(srv, n) for n in names])
    for n, o in zip(names, out):
        data = files[n]
        check(o['result'] == 0, o)
        check(o['size_download'] == len(data), (n, o))
        check(o['written'] == len(data), (n, o))
        check(o['sum'] == csum(data), (n, o))
        check(o['dlnow'] == len(data), (n, o))
        check(o['dltotal'] in (0, len(data)), (n, o))
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_mixed(env):
    """uploads and downloads alternating on one data connection"""
    srv = env.server(files={'r': os.urandom(100000)})
    up = os.urandom(77777)
    outp = os.path.join(env.tmp, 'mixed-r')
    env.run_curl(ops(['-T', env.file('u', up), url(srv, 'u')],
                     [url(srv, 'r'), '-o', outp],
                     ['-T', env.file('u', up), url(srv, 'u2')]))
    check_files(srv, {'u': up, 'u2': up})
    with open(outp, 'rb') as f:
        check(f.read() == srv.cfg.files['r'], 'download differs')
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_range(env):
    """partial (ranged) download: ABOR, like in stream mode"""
    data = os.urandom(200000)
    srv = env.server(files={'r': data})
    outp = os.path.join(env.tmp, 'range-r')
    env.run_curl(['--ftp-block-mode', '-r', '0-999', url(srv, 'r'),
                  '-o', outp])
    with open(outp, 'rb') as f:
        check(f.read() == data[:1000], 'ranged download differs')


def test_refused(env):
    """MODE B refused: stream mode, not asked again"""
    for reply in ('504 Unsupported transfer mode.', '502 Not implemented.',
                  '500 Unknown command.', '501 Syntax error.',
                  '202 Superfluous.', '450 Not now.'):
        srv = env.server(mode_b_reply=reply)
        args, files = upload_args(env, srv, [0, 1000, 70000])
        env.run_curl(['--ftp-block-mode'] + args)
        check_files(srv, files)
        check(srv.count('MODE') == 1, 'MODE sent %d times' %
              srv.count('MODE'))
        check(data_setups(srv) == 3, 'data setups: %d' % data_setups(srv))
        check('reuse' not in srv.events, srv.events)
        out = env.run_client(['info', 'block', url(srv)])
        check(out[0]['result'] == 0 and out[0]['mode'] == 0, out)


def test_retry_425(env):
    """425 on the kept connection: one retry with a new EPSV"""
    srv = env.server(reject_reuse=1)
    args, files = upload_args(env, srv, [10, 20000, 30])
    env.run_curl(['--ftp-block-mode'] + args)
    check_files(srv, files)
    check('reject-reuse' in srv.events, srv.events)
    check(data_setups(srv) == 2, 'data setups: %d' % data_setups(srv))
    # downloads, and a RETR with REST
    data = os.urandom(50000)
    srv = env.server(files={'g': data, 'h': data}, reject_reuse=1)
    o1 = os.path.join(env.tmp, 'r425-g')
    o2 = os.path.join(env.tmp, 'r425-h')
    env.run_curl(ops([url(srv, 'g'), '-o', o1],
                     ['-r', '1000-', url(srv, 'h'), '-o', o2]))
    with open(o1, 'rb') as f:
        check(f.read() == data, 'download differs')
    with open(o2, 'rb') as f:
        check(f.read() == data[1000:], 'resumed download differs')
    check(srv.count('REST') == 2, srv.log)
    check(data_setups(srv) == 2, 'data setups: %d' % data_setups(srv))
    # a 425 to the retried command is an error, no second retry
    srv = env.server(reject_at=(1, 2))
    args, files = upload_args(env, srv, [10, 20])
    env.run_curl(['--ftp-block-mode'] + args, expect=25)
    check(data_setups(srv) == 2, 'data setups: %d' % data_setups(srv))
    check(srv.count('STOR') == 3, srv.log)
    # a 425 on a new data connection is an error, no retry
    srv = env.server(reject_at=(0,))
    args, files = upload_args(env, srv, [10])
    env.run_curl(['--ftp-block-mode'] + args, expect=25)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_truncated(env):
    """data connection closed before the EOF block: error"""
    srv = env.server(files={'t': os.urandom(10000)}, truncate_download=True)
    env.run_curl(['--ftp-block-mode', url(srv, 't'), '-o',
                  os.path.join(env.tmp, 'trunc')], expect=18)
    srv = env.server(files={'t': os.urandom(10000)}, truncate_download=True)
    env.run_curl(['--ftp-block-mode', '--ignore-content-length',
                  url(srv, 't'), '-o', os.path.join(env.tmp, 'trunc')],
                 expect=18)
    srv = env.server(listing=LISTING, truncate_download=True)
    env.run_curl(['--ftp-block-mode', url(srv), '-o',
                  os.path.join(env.tmp, 'trunc')], expect=18)


def test_bad_descriptor(env):
    """invalid block descriptor: error"""
    srv = env.server(files={'t': os.urandom(1000)}, bad_descriptor=True)
    env.run_curl(['--ftp-block-mode', url(srv, 't'), '-o',
                  os.path.join(env.tmp, 'bad')], expect=8)


def test_abort(env):
    """read callback abort: data connection closed without EOF block"""
    srv = env.server()
    out = env.run_client(['abort', 'block', url(srv, 'ab'), '200000',
                          '70000'])
    check(out[0]['result'] == 42, out)
    deadline = time.time() + 5
    while 'upload-truncated' not in srv.events and time.time() < deadline:
        time.sleep(0.05)
    check('upload-truncated' in srv.events, srv.events)
    check('upload-eof' not in srv.events, srv.events)
    # same after a reuse
    srv = env.server()
    env.run_client(['upload', 'block', url(srv), '1000'])
    out = env.run_client(['abort', 'block', url(srv, 'ab'), '5000', '100'])
    check(out[0]['result'] == 42, out)


def test_reply_226(env):
    """226 instead of 250: the data connection is not reused"""
    srv = env.server(reply_226=True)
    args, files = upload_args(env, srv, [1, 100000, 0])
    env.run_curl(['--ftp-block-mode'] + args)
    check_files(srv, files)
    check(data_setups(srv) == 3, 'data setups: %d' % data_setups(srv))
    check('reuse' not in srv.events, srv.events)


def test_junk_after_eof(env):
    """bytes after the EOF block: transfer ok, connection not reused"""
    srv = env.server(files={'j': os.urandom(1000), 'k': b'kk'},
                     junk_after_eof=True)
    o1 = os.path.join(env.tmp, 'junk-j')
    o2 = os.path.join(env.tmp, 'junk-k')
    env.run_curl(['--ftp-block-mode', '--ignore-content-length',
                  url(srv, 'j'), '-o', o1, url(srv, 'k'), '-o', o2])
    with open(o1, 'rb') as f:
        check(f.read() == srv.cfg.files['j'], 'download differs')
    with open(o2, 'rb') as f:
        check(f.read() == b'kk', 'download differs')
    check(data_setups(srv) == 2, 'data setups: %d' % data_setups(srv))


def test_kept_closed(env):
    """server closes the idle kept connection: a new one is set up"""
    srv = env.server(close_kept_after=0.1)
    out = env.run_client(['upload', 'block', url(srv), '100', '200', '300'],
                         env={'MODEB_PAUSE_MS': '500'})
    check(all(o['result'] == 0 for o in out), out)
    check_files(srv, {'up0': pattern(100), 'up1': pattern(200),
                      'up2': pattern(300)})
    check(data_setups(srv) == 3, 'data setups: %d' % data_setups(srv))


def test_active(env):
    """active mode (EPRT/PORT) keeps the data connection"""
    srv = env.server(files={'a': os.urandom(40000)})
    args, files = upload_args(env, srv, [0, 5, 70000])
    outp = os.path.join(env.tmp, 'act-a')
    env.run_curl(ops(['-P', '127.0.0.1'] + args,
                     ['-P', '127.0.0.1', url(srv, 'a'), '-o', outp]))
    check_files(srv, files)
    with open(outp, 'rb') as f:
        check(f.read() == srv.cfg.files['a'], 'download differs')
    check(srv.count('EPRT') == 1, srv.log)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))
    # PORT without EPRT
    srv = env.server()
    args, files = upload_args(env, srv, [1, 2, 3])
    env.run_curl(['--ftp-block-mode', '-P', '127.0.0.1',
                  '--disable-eprt'] + args)
    check_files(srv, files)
    check(srv.count('PORT') == 1, srv.log)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))


def test_ftps(env):
    """FTPS explicit, PROT P: the TLS data connection is reused"""
    if not env.tls_ctx:
        raise Skip('no openssl to make a certificate')
    srv = env.server(files={'s': os.urandom(300000)}, listing=LISTING)
    args, files = upload_args(env, srv, SIZES[:5])
    outp = os.path.join(env.tmp, 'tls-s')
    tls = ['--ssl-reqd', '-k']
    env.run_curl(ops(tls + args, tls + [url(srv, 's'), '-o', outp],
                     tls + args[:6]))
    check_files(srv, files)
    with open(outp, 'rb') as f:
        check(f.read() == srv.cfg.files['s'], 'download differs')
    check(srv.count('AUTH') == 1 and 'PROT P' in srv.log, srv.log)
    check(data_setups(srv) == 1, 'data setups: %d' % data_setups(srv))
    out = env.run_client(['upload', 'block', url(srv), '0', '1', '65536'],
                         env={'MODEB_FTPS': '1', 'MODEB_PAUSE_MS': '200'})
    check(all(o['result'] == 0 and o['mode'] == 1 for o in out), out)


def test_stream_option(env):
    """CURLFTPMODE_STREAM (default): no MODE command"""
    srv = env.server(files={'x': os.urandom(1000)})
    args, files = upload_args(env, srv, [0, 10, 70000])
    env.run_curl(args + ['--next', url(srv, 'x'), '-o',
                         os.path.join(env.tmp, 'sx')])
    check_files(srv, files)
    check(srv.count('MODE') == 0, srv.log)
    check(data_setups(srv) == 4, 'data setups: %d' % data_setups(srv))
    out = env.run_client(['info', 'stream', url(srv)])
    check(out[0]['result'] == 0 and out[0]['mode'] == 0, out)
    out = env.run_client(['upload', 'stream', url(srv), '10', '20'])
    check(all(o['result'] == 0 and o['mode'] == 0 for o in out), out)
    check(srv.count('MODE') == 0, srv.log)


def test_info(env):
    """CURLINFO_FTP_TRANSFER_MODE after a login-only perform"""
    srv = env.server()
    out = env.run_client(['info', 'block', url(srv)])
    check(out[0]['result'] == 0 and out[0]['mode'] == 1, out)
    check(srv.log.count('MODE B') == 1, srv.log)
    check(data_setups(srv) == 0, srv.log)
    srv = env.server(mode_b_reply='504 Unsupported transfer mode.')
    out = env.run_client(['info', 'block', url(srv)])
    check(out[0]['result'] == 0 and out[0]['mode'] == 0, out)


TESTS = [v for k, v in sorted(globals().items()) if k.startswith('test_')]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument('--build', required=True,
                    help='CMake build directory of this curl')
    ap.add_argument('-k', dest='filter', default='',
                    help='run tests whose name contains this')
    ap.add_argument('-v', dest='verbose', action='store_true')
    args = ap.parse_args()
    env = Env(args)
    passed = failed = skipped = 0
    for t in TESTS:
        name = t.__name__[5:]
        if args.filter not in name:
            continue
        start = time.time()
        try:
            t(env)
            passed += 1
            print('PASS %-24s %5.2fs  %s' % (name, time.time() - start,
                                            t.__doc__))
        except Skip as e:
            skipped += 1
            print('SKIP %-24s %s' % (name, e))
        except Exception as e:  # noqa: BLE001
            failed += 1
            print('FAIL %-24s %s' % (name, t.__doc__))
            if isinstance(e, Failure):
                print('     %s' % e)
            else:
                traceback.print_exc()
    print('%d passed, %d failed, %d skipped' % (passed, failed, skipped))
    if not args.verbose:
        shutil.rmtree(env.tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
