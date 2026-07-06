# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2026  Codimension
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

"""Thread bookkeeping helpers for the remote debugger client."""


def filter_active_threads(threads, os_thread_ids, keep_greenlets=False):
    """
    Keeps debugger thread entries that still map to running OS threads.

    Greenlet contexts use greenlet object ids and must be retained separately.
    """
    if not keep_greenlets:
        return {thread_id: thread for thread_id, thread in threads.items() if thread_id in os_thread_ids}
    return {
        thread_id: thread
        for thread_id, thread in threads.items()
        if thread_id in os_thread_ids or getattr(thread, "isGreenlet", False)
    }
