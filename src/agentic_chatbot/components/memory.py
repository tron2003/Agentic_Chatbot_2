import os
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

DB_URI = os.getenv("DB_URI")


class MemoryLoader:

    def __init__(self):
        self._pool = None

    async def close(self):
        if self._pool is not None:
            await self._pool.close()

    async def load_memory(self):
        if not DB_URI:
            print("DB_URI not set — falling back to in-memory checkpoint")
            return MemorySaver()

        try:
            from psycopg_pool import AsyncConnectionPool
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            # Pool stays open for the full app lifetime
            pool = AsyncConnectionPool(
                conninfo=DB_URI,
                max_size=10,
                kwargs={"autocommit": True, "prepare_threshold": 0},
                open=False,
            )
            await pool.open()
            self._pool = pool

            saver = AsyncPostgresSaver(pool)
            await saver.setup()  # creates checkpoint tables if they don't exist
            print("Using PostgreSQL persistent checkpoint")
            return saver

        except Exception as e:
            print(f"PostgreSQL checkpoint failed ({e}) — falling back to in-memory")
            return MemorySaver()
