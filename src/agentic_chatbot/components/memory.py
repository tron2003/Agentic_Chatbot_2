from langgraph.checkpoint.postgres import PostgresSaver


DB_URI = (
    "postgresql://postgres:postgres@localhost:5442/langgraph"
)


class MemoryLoader:

    def load_memory(self):

        return PostgresSaver.from_conn_string(
            DB_URI
        )