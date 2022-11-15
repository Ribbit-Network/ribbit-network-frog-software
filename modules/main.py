

async def _main():
    pass

if __name__ == "__main__":
    import uasyncio as asyncio
    asyncio.create_task(_main())
    asyncio.get_event_loop().run_forever()
