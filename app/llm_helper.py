from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

load_dotenv()
import os

class LLMHelper:

    def __init__(self,model_provider:str = None, model:str = None,api_key:str = None) -> None:
        self.model_provider = model_provider or os.getenv('DEFAULT_MODEL_PROVIDER', 'anthropic')
        self.model = model or os.getenv('DEFAULT_MODEL')
        self.api_key = api_key or os.getenv('DEFAULT_API_KEY')

    @lru_cache(maxsize=1)
    def get_llm(self):
        if self.model_provider.lower() == 'anthropic':
            return ChatAnthropic(api_key=self.api_key, model_name=self.model)
        elif self.model_provider.lower() == 'openrouter':
            print('OpenRouter model invoked')
            return ChatOpenRouter(api_key=os.getenv('OPENROUTER_API_KEY'),model=os.getenv('OPENROUTER_MODEL'),temperature=0)

