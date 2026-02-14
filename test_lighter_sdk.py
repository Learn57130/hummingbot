import asyncio
import lighter
import json

async def main():
    async with lighter.ApiClient() as client:
        order_api = lighter.OrderApi(client)
        try:
            books = await order_api.order_books()
            print("Order Books keys:", books.keys() if hasattr(books, 'keys') else "Not a dict")
            # If it's a list or object, print structure
            print(books)
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
