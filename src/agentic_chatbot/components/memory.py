import os
from dotenv import load_dotenv
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv()

DB_URI = os.getenv("DB_URI")


class MemoryLoader:

    def load_memory(self):

        return PostgresSaver.from_conn_string(
            DB_URI
        )        