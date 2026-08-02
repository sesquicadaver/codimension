async def top_level():
    return 1


class Service:
    async def method(self):
        async def nested():
            return 2

        return await nested()
