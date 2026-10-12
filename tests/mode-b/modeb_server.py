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
"""A small FTP server implementing block mode (MODE B, RFC 959 3.4.2) with
a kept data connection, as specified for curl's CURLFTPMODE_BLOCK, plus
fault injection for tests. Python 3 standard library only.

Wire format: 3-byte header (descriptor, 16-bit big-endian length) and the
payload. EOF is descriptor 0x40. A successful block mode transfer keeps the
data connection open and replies 250; the next transfer command without a
PASV/EPSV/PORT/EPRT reuses it and gets 125.
"""

import os
import socket
import ssl
import struct
import threading
import time

EOF = 0x40
RESTART = 0x10


class Truncated(Exception):
    pass


class BadDescriptor(Exception):
    pass


class Config:
    """Behaviour of the server, changed by the tests."""

    def __init__(self):
        self.mode_b_reply = '200 Mode set to B.'  # reply to MODE B
        self.block_size = 65535          # payload per block when sending
        self.eof_on_data = False         # EOF flag on the last data block
        self.split_writes = False        # send one byte per write
        self.restart_marker = False      # send a restart marker block first
        self.truncate_download = False   # close before the EOF block
        self.bad_descriptor = False      # send descriptor 0x01
        self.reply_226 = False           # close the data conn after success
        self.slow_read = False           # read uploads slowly
        self.reject_reuse = 0            # 425 to the next N reuses
        self.reject_at = ()              # 425 to these transfer commands
                                         # (0-based), whatever the setup
        self.junk_after_eof = False      # send bytes after the EOF block
        self.close_kept_after = None     # close kept data conn after N secs
        self.files = {}                  # name -> bytes served by RETR
        self.listing = b''               # LIST/NLST payload
        self.tls_ctx = None              # server ssl.SSLContext for FTPS


class Session:
    def __init__(self, server, conn):
        self.server = server
        self.cfg = server.cfg
        self.ctrl = conn
        self.rfile = None
        self.block = False
        self.prot_p = False
        self.pending = None       # ('pasv', listener) or ('port', addr)
        self.kept = None          # kept data socket
        self.rest = 0
        self.cwd = '/'
        self.xfers = 0            # transfer commands so far
        self.log = server.log
        self.events = server.events

    # control connection helpers
    def reply(self, line):
        self.ctrl.sendall((line + '\r\n').encode())

    def readline(self):
        line = b''
        while not line.endswith(b'\n'):
            c = self.ctrl.recv(1)
            if not c:
                return None
            line += c
        return line.decode('latin-1').rstrip('\r\n')

    def close_kept(self):
        if self.kept:
            try:
                self.kept.close()
            except OSError:
                pass
            self.kept = None

    def close_pending(self):
        if self.pending and self.pending[0] == 'pasv':
            self.pending[1].close()
        self.pending = None

    # data connection
    def open_data(self):
        kind, what = self.pending
        self.pending = None
        if kind == 'pasv':
            what.settimeout(10)
            s, _ = what.accept()
            what.close()
        else:
            s = socket.create_connection(what, timeout=10)
        s.settimeout(30)
        if self.prot_p:
            s = self.cfg.tls_ctx.wrap_socket(s, server_side=True)
        return s

    def get_data_conn(self):
        """Return (socket, reused) or (None, False) after replying 425."""
        n = self.xfers
        self.xfers += 1
        if n in self.cfg.reject_at:
            self.events.append('reject')
            self.close_kept()
            self.close_pending()
            self.reply('425 Can not open data connection.')
            return None, False
        if self.pending:
            self.close_kept()
            s = self.open_data_announced()
            return s, False
        if self.kept and self.block:
            if self.cfg.reject_reuse > 0:
                self.cfg.reject_reuse -= 1
                self.events.append('reject-reuse')
                self.close_kept()
                self.reply('425 Use PORT or PASV first.')
                return None, False
            self.events.append('reuse')
            self.reply('125 Data connection already open; transfer '
                       'starting.')
            s = self.kept
            self.kept = None
            return s, True
        self.reply('425 Use PORT or PASV first.')
        return None, False

    def open_data_announced(self):
        if self.pending[0] == 'port':
            self.reply('150 Opening data connection.')
            s = self.open_data()
        else:
            # accept first so that a TLS handshake can follow the reply
            self.reply('150 Opening data connection.')
            s = self.open_data()
        self.events.append('new-data-conn')
        return s

    def finish_ok(self, s):
        if self.block and not self.cfg.reply_226:
            self.kept = s
            self.reply('250 Transfer complete.')
            if self.cfg.close_kept_after is not None:
                delay = self.cfg.close_kept_after
                kept = s

                def closer():
                    time.sleep(delay)
                    try:
                        kept.close()
                    except OSError:
                        pass
                threading.Thread(target=closer, daemon=True).start()
        else:
            self.shutdown_data(s)
            self.reply('226 Transfer complete.')

    def shutdown_data(self, s):
        try:
            if isinstance(s, ssl.SSLSocket):
                try:
                    s = s.unwrap()
                except (OSError, ValueError):
                    pass
            s.close()
        except OSError:
            pass

    def fail(self, s, line):
        try:
            s.close()
        except OSError:
            pass
        self.reply(line)

    # block mode framing
    def recv_exact(self, s, n):
        buf = b''
        while len(buf) < n:
            want = n - len(buf)
            if self.cfg.slow_read:
                want = min(want, 16384)
                time.sleep(0.001)
            try:
                d = s.recv(want)
            except ssl.SSLEOFError:
                d = b''
            if not d:
                raise Truncated()
            buf += d
        return buf

    def recv_blocks(self, s, out):
        while True:
            hdr = self.recv_exact(s, 3)
            desc, length = hdr[0], struct.unpack('>H', hdr[1:])[0]
            if desc & 0x0f:
                raise BadDescriptor()
            payload = self.recv_exact(s, length) if length else b''
            if not desc & RESTART:
                out.append(payload)
            if desc & EOF:
                return

    def send_raw(self, s, data):
        if self.cfg.split_writes:
            for i in range(len(data)):
                s.sendall(data[i:i + 1])
                if i % 7 == 0:
                    time.sleep(0.001)
        else:
            s.sendall(data)

    def send_blocks(self, s, data):
        cfg = self.cfg
        out = b''
        if cfg.restart_marker:
            out += bytes([RESTART]) + struct.pack('>H', 8) + b'MARKER00'
        if cfg.bad_descriptor:
            out += bytes([0x01]) + struct.pack('>H', len(data)) + data
            self.send_raw(s, out)
            return
        pos = 0
        chunks = []
        while pos < len(data):
            chunks.append(data[pos:pos + cfg.block_size])
            pos += cfg.block_size
        for i, c in enumerate(chunks):
            last = i == len(chunks) - 1
            desc = EOF if (last and cfg.eof_on_data and
                           not cfg.truncate_download) else 0
            if i == 0 and len(chunks) > 1:
                # a zero-length non-EOF block is legal, and ignored
                out += b'\x00\x00\x00'
            out += bytes([desc]) + struct.pack('>H', len(c)) + c
        if cfg.truncate_download:
            self.send_raw(s, out)
            return
        if not (cfg.eof_on_data and chunks):
            out += b'\x40\x00\x00'
        if cfg.junk_after_eof:
            out += b'JUNK'
        self.send_raw(s, out)

    # commands
    def do_transfer_upload(self, name, append):
        s, reused = self.get_data_conn()
        if not s:
            return
        path = os.path.join(self.server.root, name.lstrip('/'))
        parts = []
        try:
            if self.block:
                self.recv_blocks(s, parts)
            else:
                while True:
                    d = s.recv(65536)
                    if not d:
                        break
                    parts.append(d)
        except Truncated:
            self.events.append('upload-truncated')
            self.write_file(path, parts, append)
            self.fail(s, '426 Connection closed; transfer aborted.')
            return
        except BadDescriptor:
            self.events.append('upload-bad-descriptor')
            self.fail(s, '426 Connection closed; transfer aborted.')
            return
        self.write_file(path, parts, append)
        self.events.append('upload-eof' if self.block else 'upload-close')
        self.finish_ok(s)

    def write_file(self, path, parts, append):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'ab' if append else 'wb') as f:
            for p in parts:
                f.write(p)

    def do_transfer_download(self, data):
        s, reused = self.get_data_conn()
        if not s:
            return
        try:
            if self.block:
                self.send_blocks(s, data)
                if self.cfg.truncate_download or self.cfg.bad_descriptor:
                    time.sleep(0.2)
                    self.fail(s, '426 Connection closed; transfer aborted.')
                    return
            else:
                s.sendall(data)
        except OSError:
            self.fail(s, '426 Connection closed; transfer aborted.')
            return
        self.finish_ok(s)

    def handle(self):
        self.reply('220 MODE B test server')
        while True:
            line = self.readline()
            if line is None:
                break
            self.log.append(line)
            cmd, _, arg = line.partition(' ')
            cmd = cmd.upper()
            if not self.dispatch(cmd, arg):
                break
        self.close_kept()
        self.close_pending()

    def dispatch(self, cmd, arg):
        cfg = self.cfg
        if cmd == 'USER':
            self.reply('331 Password please.')
        elif cmd == 'PASS':
            self.reply('230 Logged in.')
        elif cmd == 'AUTH':
            if not cfg.tls_ctx:
                self.reply('500 No TLS.')
            else:
                self.reply('234 AUTH TLS ok.')
                self.ctrl = cfg.tls_ctx.wrap_socket(self.ctrl,
                                                    server_side=True)
        elif cmd == 'PBSZ':
            self.reply('200 PBSZ=0')
        elif cmd == 'PROT':
            self.prot_p = arg.upper() == 'P'
            self.reply('200 PROT ok.')
        elif cmd == 'PWD':
            self.reply('257 "%s" is the current directory' % self.cwd)
        elif cmd == 'SYST':
            self.reply('215 UNIX Type: L8')
        elif cmd == 'TYPE':
            self.reply('200 Type set.')
        elif cmd == 'MODE':
            a = arg.strip().upper()
            if not a:
                self.reply('501 Usage: MODE <S|B>')
            elif a == 'S':
                self.block = False
                self.close_kept()
                self.reply('200 Mode set to S.')
            elif a == 'B':
                self.reply(cfg.mode_b_reply)
                if cfg.mode_b_reply.startswith('200'):
                    self.block = True
            else:
                self.reply('504 Unsupported transfer mode.')
        elif cmd in ('CWD', 'MKD'):
            self.reply('250 OK.' if cmd == 'CWD' else '257 Created.')
        elif cmd == 'SIZE':
            data = cfg.files.get(arg.lstrip('/'))
            path = os.path.join(self.server.root, arg.lstrip('/'))
            if data is not None:
                self.reply('213 %d' % len(data))
            elif os.path.exists(path):
                self.reply('213 %d' % os.path.getsize(path))
            else:
                self.reply('550 No such file.')
        elif cmd == 'REST':
            self.rest = int(arg)
            self.reply('350 Restarting.')
        elif cmd in ('EPSV', 'PASV'):
            self.close_kept()
            self.close_pending()
            lst = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            lst.bind(('127.0.0.1', 0))
            lst.listen(1)
            port = lst.getsockname()[1]
            self.pending = ('pasv', lst)
            if cmd == 'EPSV':
                self.reply('229 Entering Extended Passive Mode (|||%d|)' %
                           port)
            else:
                self.reply('227 Entering Passive Mode (127,0,0,1,%d,%d)' %
                           (port >> 8, port & 255))
        elif cmd in ('EPRT', 'PORT'):
            self.close_kept()
            self.close_pending()
            if cmd == 'EPRT':
                d = arg[0]
                _, proto, host, port, _ = arg.split(d)
                addr = (host, int(port))
            else:
                n = [int(x) for x in arg.split(',')]
                addr = ('%d.%d.%d.%d' % tuple(n[:4]), n[4] * 256 + n[5])
            self.pending = ('port', addr)
            self.reply('200 PORT ok.')
        elif cmd in ('STOR', 'APPE'):
            self.do_transfer_upload(arg, cmd == 'APPE')
        elif cmd == 'RETR':
            data = cfg.files.get(arg.lstrip('/'))
            if data is None:
                path = os.path.join(self.server.root, arg.lstrip('/'))
                if os.path.exists(path):
                    with open(path, 'rb') as f:
                        data = f.read()
            if data is None:
                self.reply('550 No such file.')
            else:
                data = data[self.rest:]
                self.rest = 0
                self.do_transfer_download(data)
        elif cmd in ('LIST', 'NLST', 'MLSD'):
            self.do_transfer_download(cfg.listing)
        elif cmd == 'DELE':
            self.reply('250 Deleted.')
        elif cmd == 'NOOP':
            self.reply('200 NOOP ok.')
        elif cmd == 'QUIT':
            self.reply('221 Bye.')
            return False
        else:
            self.reply('500 Unknown command.')
        return True


class Server:
    def __init__(self, root, cfg=None):
        self.root = root
        self.cfg = cfg or Config()
        self.log = []        # control commands, all sessions
        self.events = []     # data connection events
        self.sessions = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.sessions += 1
            t = threading.Thread(target=self.run_session, args=(conn,),
                                 daemon=True)
            t.start()

    def run_session(self, conn):
        s = Session(self, conn)
        try:
            s.handle()
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            try:
                s.ctrl.close()
            except OSError:
                pass

    def count(self, verb):
        return sum(1 for line in self.log
                   if line.split(' ')[0].upper() == verb)

    def close(self):
        self.sock.close()


if __name__ == '__main__':
    import argparse
    import tempfile
    ap = argparse.ArgumentParser(description='MODE B test FTP server')
    ap.add_argument('--root', default=None)
    args = ap.parse_args()
    root = args.root or tempfile.mkdtemp()
    srv = Server(root)
    print('listening on 127.0.0.1:%d, root %s' % (srv.port, root),
          flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
