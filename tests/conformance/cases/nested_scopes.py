class Outer:
    def method(self):
        if True:
            self.flag = 1

            def nested():
                return 2

            async def anested():
                return 3

            return nested()
