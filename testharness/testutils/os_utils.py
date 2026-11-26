"""Names of the effective user and group.

Plain strings: rephelp formats them straight into the squid config.
"""
import grp
import os
import pwd


def _userName(uid):
    try:
        return pwd.getpwuid(uid).pw_name
    except KeyError:
        return str(uid)


def _groupName(gid):
    try:
        return grp.getgrgid(gid).gr_name
    except KeyError:
        return str(gid)


effectiveUser = _userName(os.geteuid())
effectiveGroup = _groupName(os.getegid())
