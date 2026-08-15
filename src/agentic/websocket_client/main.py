import asyncio
import uuid

from websockets import connect


async def main():
    chat_id = uuid.uuid4().__str__()
    async with connect(f"ws://localhost:5000/ws/{chat_id}") as websocket:
        while True:
            message = "Hey"
            if message.lower() == "exit":
                break
            await websocket.send(message)
            response = await websocket.recv()
            print(f"Received: {response}")


if __name__ == "__main__":
    asyncio.run(main())
