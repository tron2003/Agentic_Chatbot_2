RAG_PROMPT = """

Retrieved Context:

{context}

Instructions:

1. Answer using retrieved context.
2. Use chat memory when useful.
3. If context lacks information,
   say information not found.
4. Do not invent facts.

"""