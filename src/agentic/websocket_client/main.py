import asyncio

from websockets import connect


async def main():
    async with connect("ws://localhost:5000/ws/test_chat") as websocket:
        while True:
            message = "Hey"
            if message.lower() == "exit":
                break
            await websocket.send(message)
            response = await websocket.recv()
            print(f"Received: {response}")


if __name__ == "__main__":
    asyncio.run(main())
