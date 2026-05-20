import yaml
from langchain_openai import ChatOpenAI


class LLMLoader:

    def __init__(self):

        with open(
            "config/config.yaml",
            "r"
        ) as file:

            self.config = yaml.safe_load(file)

    def load_llm(self):

        llm_config = self.config["llm"]["local"]

        llm = ChatOpenAI(

            model=llm_config["model_name"],

            api_key=llm_config["api_key"],

            base_url=llm_config["base_url"]

        )

        return llm