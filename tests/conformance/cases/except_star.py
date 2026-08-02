async def run():
    try:
        await something()
    except* ValueError as err:
        return err
