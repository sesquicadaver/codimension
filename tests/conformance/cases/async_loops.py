async def walk(items):
    async for x in items:
        async with lock:
            yield x


def sync_walk(items):
    for x in items:
        with open("f") as fh:
            fh.write(str(x))
