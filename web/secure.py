import os
import time
import fcntl
import hmac
import binascii
import sys
import hashlib

import bottle

import config

__all__ = ["get_csrf_blob", "check_csrf_blob", "setup_csrf", "get_user_hash"]

HASH=hashlib.sha1

def get_user_hash():
    verify = bottle.request.environ.get('SSL_CLIENT_VERIFY', '')
    if not (verify == 'GENEROUS' or verify == 'SUCCESS'):
        return 'FAILVERIFY'
    blob = bottle.request.environ.get('SSL_CLIENT_CERT')
    if not blob:
        return 'NOCERT'

    b64 = ''.join(l for l in blob.split('\n')
        if not l.startswith('-'))

    return HASH(binascii.a2b_base64(b64)).hexdigest()

def setup_csrf():
    NONCE_SIZE=16
    global _csrf_fd, _csrf_key
    _csrf_fd = open('%s/csrf.dat' % config.DATA_PATH, 'r+')

    try:
        fcntl.lockf(_csrf_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.fchmod(_csrf_fd.fileno(), 0600)
        _csrf_fd.write("%d-%s" % (os.getpid(), binascii.hexlify(os.urandom(NONCE_SIZE))))
        _csrf_fd.flush()
        _csrf_fd.seek(0)
    except IOError:
        pass
    fcntl.lockf(_csrf_fd, fcntl.LOCK_SH)
    _csrf_key = _csrf_fd.read()
    # keep the lock open until we go away


def get_csrf_blob():
    expiry = int(config.CSRF_TIMEOUT + time.time())
    content = '%s-%s' % (get_user_hash(), expiry)
    mac = hmac.new(_csrf_key, content).hexdigest()
    return "%s-%s" % (content, mac)

def check_csrf_blob(blob):
    toks = blob.split('-')
    if len(toks) != 3:
        print>>sys.stderr, "wrong toks"
        return False

    user, expiry, mac = toks
    if user != get_user_hash():
        print>>sys.stderr, "wrong user"
        return False

    try:
        exp = int(expiry)
    except ValueError:
        print>>sys.stderr, "failed exp"
        return False

    if exp < 1000000000:
        return False

    if exp < time.time():
        print>>sys.stderr, "expired %d %d" % (exp, time.time())
        return False

    check_content = "%s-%s" % (user, expiry)
    check_mac = hmac.new(_csrf_key, check_content).hexdigest()
    if mac == check_mac:
        print>>sys.stderr, "good hmac"
        return True

    print>>sys.stderr, "fail"
    return False

