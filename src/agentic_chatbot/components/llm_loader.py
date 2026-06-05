import os
import yaml
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama

load_dotenv()


class LLMLoader:

    def __init__(self):

        with open("config/config.yaml", "r") as file:

            self.config = yaml.safe_load(file)

    def load_llm(self):

        provider = self.config["llm"]["active_provider"]

        if provider == "local":

            llm_config = self.config["llm"]["local"]

            return ChatOpenAI(
                model=llm_config["model_name"],
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"],
            )

        elif provider == "local2":

            llm_config = self.config["llm"]["local2"]

            return ChatOllama(
                model=llm_config["model_name"],
                base_url=llm_config["base_url"],
                temperature=llm_config.get("temperature", 0.5),
            )

        elif provider == "claude":

            llm_config = self.config["llm"]["claude"]

            return ChatAnthropic(
                model=llm_config["model_name"],
                api_key=os.getenv("ANTHROPIC_API_KEY"),
                temperature=llm_config["temperature"],
            )
        elif provider == "openrouter":

            llm_config = self.config["llm"]["openrouter"]

            return ChatOpenAI(
                model=llm_config["model_name"],
                api_key=os.getenv("OPENROUTER_API_KEY"),
                base_url=llm_config["base_url"],
                temperature=llm_config.get("temperature", 0.5),
            )
        raise ValueError(f"Unknown provider: {provider}")
