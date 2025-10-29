import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os
from dotenv import load_dotenv

load_dotenv()

# Convert to async URL
url = os.getenv("DATABASE_URL", "")
if "psycopg2" in url:
    url = url.replace("postgresql+psycopg2", "postgresql+asyncpg")

engine = create_async_engine(url, echo=True)

async def main():
    try:
        async with engine.begin() as conn:
            result = await conn.execute("SELECT version();")
            version = result.scalar_one()
            print("✅ Connected to PostgreSQL!")
            print("Database version:", version)
    except Exception as e:
        print("❌ Connection failed:", e)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
